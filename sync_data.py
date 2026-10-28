"""Download Penn State games and play-by-play, then idempotently upsert to TiDB."""

import json
import os
import re
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime
from pathlib import Path

import mysql.connector

from db import DATABASE, _read_local_env, connect


API_BASE = "https://api.collegefootballdata.com"
TEAM_NAME = "Penn State"
SEASON_TYPE = "regular"
WEEKS_PER_SEASON = 15

GAME_COLUMNS = (
	"game_id",
	"season",
	"week",
	"start_date",
	"opponent",
	"location",
	"penn_state_points",
	"opponent_points",
	"result",
)

PLAY_COLUMNS = (
	"game_id",
	"play_id",
	"season",
	"week",
	"opponent",
	"unit",
	"offense",
	"defense",
	"quarter",
	"score_state",
	"penn_state_score_before_play",
	"opponent_score_before_play",
	"down",
	"yards_to_go",
	"play_kind",
	"yards_gained",
	"success",
	"explosive_pass_15_plus",
	"play_value_ppa",
	"scoring",
	"play_description",
)


def _api_key() -> str:
	from_env_file = _read_local_env()
	key = os.environ.get("CFBD_API_KEY") or from_env_file.get("api-key")
	if not key:
		raise RuntimeError(
			"CollegeFootballData API key not found. Add api-key to the local .env "
			"file or set CFBD_API_KEY in your environment."
		)
	return key


def _get_api_data(path: str, parameters: dict, api_key: str) -> list[dict]:
	query = urllib.parse.urlencode(parameters)
	request = urllib.request.Request(
		f"{API_BASE}{path}?{query}",
		headers={
			"Authorization": "Bearer " + api_key,
			"Accept": "application/json",
		},
	)
	try:
		with urllib.request.urlopen(request, timeout=45) as response:
			result = json.loads(response.read().decode("utf-8"))
	except urllib.error.HTTPError as error:
		if error.code in (401, 403):
			message = "CollegeFootballData rejected the API key or access to this data."
		elif error.code == 429:
			message = "CollegeFootballData's request limit was reached. Wait before syncing again."
		else:
			message = f"CollegeFootballData returned HTTP {error.code}."
		raise RuntimeError(message) from None
	except urllib.error.URLError as error:
		raise RuntimeError(
			f"Could not reach CollegeFootballData.com: {error.reason}"
		) from None
	except json.JSONDecodeError:
		raise RuntimeError("CollegeFootballData returned invalid JSON.") from None

	if not isinstance(result, list):
		raise RuntimeError("CollegeFootballData returned an unexpected response.")
	return result


def _game_record(game: dict, season: int) -> tuple | None:
	if game.get("homePoints") is None or game.get("awayPoints") is None:
		return None

	home = str(game.get("homeTeam") or "")
	away = str(game.get("awayTeam") or "")
	if home.casefold() == TEAM_NAME.casefold():
		opponent = away
		penn_state_points = int(game["homePoints"])
		opponent_points = int(game["awayPoints"])
		location = "Home"
	elif away.casefold() == TEAM_NAME.casefold():
		opponent = home
		penn_state_points = int(game["awayPoints"])
		opponent_points = int(game["homePoints"])
		location = "Away"
	else:
		return None

	result = (
		"Win"
		if penn_state_points > opponent_points
		else "Loss"
		if penn_state_points < opponent_points
		else "Tie"
	)
	start_date = game.get("startDate")
	if start_date:
		start_date = datetime.fromisoformat(
			start_date.replace("Z", "+00:00")
		).replace(tzinfo=None)
	return (
		int(game["id"]),
		int(season),
		int(game["week"]) if game.get("week") is not None else None,
		start_date,
		opponent,
		location,
		penn_state_points,
		opponent_points,
		result,
	)


def _integer(value):
	return int(value) if value is not None else None


def _play_record(play: dict, season: int, week: int) -> tuple | None:
	offense = str(play.get("offense") or "")
	defense = str(play.get("defense") or "")
	offense_is_psu = offense.casefold() == TEAM_NAME.casefold()
	defense_is_psu = defense.casefold() == TEAM_NAME.casefold()
	if not (offense_is_psu or defense_is_psu):
		return None

	unit = "Penn State offense" if offense_is_psu else "Penn State defense"
	opponent = defense if offense_is_psu else offense
	kind_text = str(play.get("playType") or "").casefold()
	if "rush" in kind_text:
		play_kind = "Rush"
	elif "pass" in kind_text or "sack" in kind_text:
		play_kind = "Pass"
	else:
		play_kind = "Other"

	period = _integer(play.get("period"))
	if period is None:
		quarter = "Unknown"
	elif 1 <= period <= 4:
		quarter = f"Q{period}"
	elif period > 4:
		quarter = f"OT{period - 4}"
	else:
		quarter = "Unknown"

	team_score = play.get("offenseScore") if offense_is_psu else play.get("defenseScore")
	other_score = play.get("defenseScore") if offense_is_psu else play.get("offenseScore")
	if team_score is None or other_score is None:
		score_state = "Unknown"
	else:
		score_state = (
			"Leading"
			if int(team_score) > int(other_score)
			else "Trailing"
			if int(team_score) < int(other_score)
			else "Tied"
		)

	down = _integer(play.get("down"))
	distance = _integer(play.get("distance"))
	yards_gained = _integer(play.get("yardsGained"))
	success = None
	if down in (1, 2, 3, 4) and distance is not None and yards_gained is not None:
		fraction = {1: 0.5, 2: 0.7, 3: 1.0, 4: 1.0}[down]
		success = yards_gained >= distance * fraction
	explosive_pass = (
		yards_gained >= 15
		if play_kind == "Pass" and yards_gained is not None
		else None
	)
	ppa = play.get("ppa")
	return (
		int(play["gameId"]),
		str(play["id"]),
		int(season),
		int(week),
		opponent,
		unit,
		offense,
		defense,
		quarter,
		score_state,
		_integer(team_score),
		_integer(other_score),
		down,
		distance,
		play_kind,
		yards_gained,
		success,
		explosive_pass,
		float(ppa) if ppa is not None else None,
		bool(play.get("scoring", False)),
		play.get("playText"),
	)


def _ensure_schema() -> None:
	connection = connect(database=None)
	cursor = connection.cursor()
	try:
		cursor.execute(
			f"CREATE DATABASE IF NOT EXISTS `{DATABASE}` "
			"CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci"
		)
		connection.commit()
	finally:
		cursor.close()
		connection.close()

	connection = connect()
	cursor = connection.cursor()
	try:
		cursor.execute(
			"""
			CREATE TABLE IF NOT EXISTS penn_state_games (
				game_id BIGINT NOT NULL PRIMARY KEY,
				season SMALLINT NOT NULL,
				week SMALLINT NULL,
				start_date DATETIME NULL,
				opponent VARCHAR(128) NOT NULL,
				location VARCHAR(8) NOT NULL,
				penn_state_points INT NOT NULL,
				opponent_points INT NOT NULL,
				result VARCHAR(8) NOT NULL
			) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci
			"""
		)
		cursor.execute(
			"""
			CREATE TABLE IF NOT EXISTS penn_state_game_plays (
				game_id BIGINT NOT NULL,
				play_id VARCHAR(128) NOT NULL,
				season SMALLINT NOT NULL,
				week SMALLINT NULL,
				opponent VARCHAR(128) NULL,
				unit VARCHAR(24) NOT NULL,
				offense VARCHAR(128) NULL,
				defense VARCHAR(128) NULL,
				quarter VARCHAR(8) NULL,
				score_state VARCHAR(16) NULL,
				penn_state_score_before_play INT NULL,
				opponent_score_before_play INT NULL,
				down TINYINT NULL,
				yards_to_go SMALLINT NULL,
				play_kind VARCHAR(8) NOT NULL,
				yards_gained SMALLINT NULL,
				success BOOLEAN NULL,
				explosive_pass_15_plus BOOLEAN NULL,
				play_value_ppa DOUBLE NULL,
				scoring BOOLEAN NOT NULL DEFAULT FALSE,
				play_description TEXT NULL,
				PRIMARY KEY (game_id, play_id),
				INDEX idx_quarter_unit (game_id, quarter, unit)
			) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci
			"""
		)
		connection.commit()
	finally:
		cursor.close()
		connection.close()


def _upsert(table: str, columns: tuple[str, ...], rows: list[tuple]) -> None:
	if not rows:
		return
	quoted_columns = ", ".join(f"`{column}`" for column in columns)
	placeholders = ", ".join(["%s"] * len(columns))
	primary_keys = (
		{"game_id"}
		if table == "penn_state_games"
		else {"game_id", "play_id"}
	)
	updates = ", ".join(
		f"`{column}` = VALUES(`{column}`)"
		for column in columns
		if column not in primary_keys
	)
	statement = (
		f"INSERT INTO `{table}` ({quoted_columns}) VALUES ({placeholders}) "
		f"ON DUPLICATE KEY UPDATE {updates}"
	)
	connection = connect()
	cursor = connection.cursor()
	try:
		for offset in range(0, len(rows), 500):
			cursor.executemany(statement, rows[offset : offset + 500])
		connection.commit()
	except mysql.connector.Error:
		connection.rollback()
		raise
	finally:
		cursor.close()
		connection.close()


def sync_seasons(seasons: list[int]) -> dict[str, int]:
	"""Fetch selected seasons and upsert games and game-relevant play-by-play."""
	if not seasons:
		raise ValueError("Choose at least one season to synchronize.")

	key = _api_key()
	games_by_id = {}
	for season in seasons:
		raw_games = _get_api_data(
			"/games",
			{"year": season, "team": TEAM_NAME, "seasonType": SEASON_TYPE},
			key,
		)
		for game in raw_games:
			row = _game_record(game, season)
			if row is not None:
				games_by_id[row[0]] = row

		if not any(game[1] == season for game in games_by_id.values()):
			raise RuntimeError(
				f"No completed Penn State games were returned for {season}."
			)

	play_records = {}
	total_weeks = len(seasons) * WEEKS_PER_SEASON
	checked_weeks = 0
	for season in seasons:
		for week in range(1, WEEKS_PER_SEASON + 1):
			week_plays = _get_api_data(
				"/plays",
				{
					"year": season,
					"week": week,
					"team": TEAM_NAME,
					"seasonType": SEASON_TYPE,
				},
				key,
			)
			for play in week_plays:
				row = _play_record(play, season, week)
				if row is not None and row[0] in games_by_id:
					play_records[(row[0], row[1])] = row
			checked_weeks += 1
			if checked_weeks % 10 == 0 or checked_weeks == total_weeks:
				print(
					f"Fetched {checked_weeks} of {total_weeks} selected season-weeks."
				)

	if not play_records:
		raise RuntimeError("No Penn State game plays were returned.")

	# Fail before writes if any selected completed game has no play-by-play.
	play_game_ids = {row[0] for row in play_records.values()}
	missing_plays = set(games_by_id).difference(play_game_ids)
	if missing_plays:
		raise RuntimeError(
			f"{len(missing_plays)} selected completed game(s) have no play-by-play; "
			"no database rows were written."
		)

	try:
		_ensure_schema()
		_upsert("penn_state_games", GAME_COLUMNS, list(games_by_id.values()))
		_upsert("penn_state_game_plays", PLAY_COLUMNS, list(play_records.values()))
	except mysql.connector.Error as error:
		raise RuntimeError(
			"Could not save the downloaded data to TiDB. Check database "
			f"permissions (connector code {getattr(error, 'errno', 'unknown')})."
		) from None

	connection = connect()
	cursor = connection.cursor()
	try:
		cursor.execute(
			"SELECT COUNT(DISTINCT game_id), COUNT(*) FROM penn_state_game_plays "
			"WHERE season IN (" + ", ".join(["%s"] * len(seasons)) + ")",
			tuple(seasons),
		)
		game_count, play_count = cursor.fetchone()
		return {
			"games_synced": len(games_by_id),
			"plays_fetched": len(play_records),
			"games_in_database": int(game_count),
			"plays_in_database": int(play_count),
		}
	finally:
		cursor.close()
		connection.close()
