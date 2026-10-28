"""Local TiDB connection and read helpers for the Penn State dashboard."""

import os
import re
from pathlib import Path

import mysql.connector
import pandas as pd


HOST = "gateway01.us-east-1.prod.aws.tidbcloud.com"
PORT = 4000
USER = "3eB6ydhjxG6RLCv.root"
DATABASE = "penn_state_analytics"


def _read_local_env() -> dict[str, str]:
	"""Read key=value pairs without printing or exporting secrets."""
	env_path = Path(__file__).resolve().with_name(".env")
	if not env_path.is_file():
		return {}

	values = {}
	for line in env_path.read_text(encoding="utf-8").splitlines():
		match = re.match(r"^\s*([^:=]{1,100})\s*[:=]\s*(.*?)\s*$", line)
		if match:
			name = match.group(1).strip().casefold().replace("_", "-")
			value = match.group(2).strip().strip("\"'")
			if value:
				values[name] = value
	return values


def _connection_options(database: str | None = DATABASE) -> dict:
	"""Build a verified TLS connection using local environment credentials."""
	from_env_file = _read_local_env()
	password = os.environ.get("TIDB_PASSWORD") or from_env_file.get(
		"database-password"
	)
	if not password:
		raise RuntimeError(
			"Database password not found. Add database-password to the local .env "
			"file or set TIDB_PASSWORD in your environment."
		)

	try:
		import certifi
	except ImportError as error:
		raise RuntimeError(
			"TLS certificate support is missing. Install the project requirements."
		) from error

	options = {
		"host": HOST,
		"port": PORT,
		"user": USER,
		"password": password,
		"connection_timeout": 15,
		"ssl_ca": certifi.where(),
		"ssl_verify_cert": True,
		"ssl_verify_identity": True,
	}
	if database:
		options["database"] = database
	return options


def connect(database: str | None = DATABASE):
	"""Open an authenticated TiDB connection with TLS verification."""
	try:
		return mysql.connector.connect(**_connection_options(database))
	except mysql.connector.Error as error:
		raise RuntimeError(
			"Could not connect to TiDB. Check network access and database "
			f"permissions (connector code {getattr(error, 'errno', 'unknown')})."
		) from None


def _read_frame(query: str, parameters: tuple = ()) -> pd.DataFrame:
	connection = connect()
	cursor = connection.cursor(dictionary=True)
	try:
		cursor.execute(query, parameters)
		return pd.DataFrame(cursor.fetchall())
	finally:
		cursor.close()
		connection.close()


def load_games() -> pd.DataFrame:
	"""Read Penn State game metadata from TiDB."""
	return _read_frame(
		"""
		SELECT game_id, season, week, start_date, opponent, location,
			penn_state_points, opponent_points, result
		FROM penn_state_games
		ORDER BY season DESC, start_date DESC, week DESC
		"""
	)


def load_game_plays(game_id: int) -> pd.DataFrame:
	"""Read one game's play-by-play rows from TiDB."""
	return _read_frame(
		"""
		SELECT game_id, play_id, season, week, opponent, unit, offense,
			defense, quarter, score_state, penn_state_score_before_play,
			opponent_score_before_play, down, yards_to_go, play_kind,
			yards_gained, success, explosive_pass_15_plus, play_value_ppa,
			scoring, play_description
		FROM penn_state_game_plays
		WHERE game_id = %s
		ORDER BY CASE
			WHEN quarter REGEXP '^Q[1-4]$' THEN CAST(SUBSTRING(quarter, 2) AS UNSIGNED)
			WHEN quarter REGEXP '^OT[0-9]+$' THEN 4 + CAST(SUBSTRING(quarter, 3) AS UNSIGNED)
			ELSE 99
		END, week, play_id
		""",
		(int(game_id),),
	)


def available_seasons() -> list[int]:
	"""Return seasons that have downloaded games."""
	games = load_games()
	if games.empty:
		return []
	return sorted(games["season"].dropna().astype(int).unique().tolist())
