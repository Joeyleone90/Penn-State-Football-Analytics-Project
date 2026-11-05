"""Flask website for exploring Penn State football games and play-by-play."""

from flask import Flask, Response, abort, render_template, request
import pandas as pd

import db


app = Flask(__name__)

QUARTER_ORDER = ["Q1", "Q2", "Q3", "Q4", "OT1", "OT2", "OT3", "OT4"]
PLAY_COLORS = {"Rush": "#1b5e3b", "Pass": "#c99a2e", "Other": "#7f8c8d"}
PLAY_COLUMNS = [
	"quarter",
	"unit",
	"score_state",
	"penn_state_score_before_play",
	"opponent_score_before_play",
	"down",
	"yards_to_go",
	"play_kind",
	"yards_gained",
	"success",
	"play_value_ppa",
	"scoring",
	"play_description",
]


def _mean_or_none(values: pd.Series) -> float | None:
	values = pd.to_numeric(values, errors="coerce").dropna()
	return float(values.mean()) if not values.empty else None


def _fmt_number(value: float | None, digits: int = 1) -> str:
	return f"{value:.{digits}f}" if value is not None and pd.notna(value) else "N/A"


def _fmt_percent(value: float | None) -> str:
	return f"{value:.1%}" if value is not None and pd.notna(value) else "N/A"


def _quarter_sort_key(quarter: str) -> tuple[int, str]:
	try:
		return QUARTER_ORDER.index(quarter), quarter
	except ValueError:
		return len(QUARTER_ORDER), quarter


def _chart_data(plays: pd.DataFrame) -> dict:
	quarters = sorted(plays["quarter"].dropna().unique().tolist(), key=_quarter_sort_key)
	play_kinds = sorted(plays["play_kind"].dropna().unique().tolist())
	datasets = []
	yards_datasets = []

	for play_kind in play_kinds:
		kind_plays = plays.loc[plays["play_kind"].eq(play_kind)]
		counts = kind_plays.groupby("quarter", observed=True).size()
		average_yards = kind_plays.groupby("quarter", observed=True)[
			"yards_gained"
		].mean()
		color = PLAY_COLORS.get(play_kind, PLAY_COLORS["Other"])
		datasets.append(
			{
				"label": play_kind,
				"data": [int(counts.get(quarter, 0)) for quarter in quarters],
				"backgroundColor": color,
			}
		)
		yards_datasets.append(
			{
				"label": play_kind,
				"data": [
					float(average_yards[quarter])
					if quarter in average_yards and pd.notna(average_yards[quarter])
					else None
					for quarter in quarters
				],
				"borderColor": color,
				"backgroundColor": color,
				"tension": 0.25,
				"spanGaps": False,
			}
		)

	return {
		"labels": quarters,
		"play_mix": datasets,
		"average_yards": yards_datasets,
	}


def _game_label(game: pd.Series) -> str:
	week = int(game["week"]) if pd.notna(game["week"]) else "?"
	return (
		f"Week {week} · {game['opponent']} · {game['result']} "
		f"({int(game['penn_state_points'])}-{int(game['opponent_points'])})"
	)


@app.get("/")
def index():
	try:
		games = db.load_games()
	except RuntimeError as error:
		app.logger.exception("Could not load game data from TiDB")
		return render_template("index.html", page_error=str(error)), 503

	if games.empty:
		return render_template("index.html", games_available=False)

	seasons = sorted(games["season"].dropna().astype(int).unique().tolist())
	requested_season = request.args.get("season", type=int)
	selected_season = requested_season if requested_season in seasons else seasons[-1]
	season_games = games.loc[games["season"].eq(selected_season)].copy()

	requested_game_id = request.args.get("game_id", type=int)
	selected_rows = season_games.loc[season_games["game_id"].eq(requested_game_id)]
	selected_game = (
		selected_rows.iloc[0] if not selected_rows.empty else season_games.iloc[0]
	)
	selected_game_id = int(selected_game["game_id"])
	game_options = [
		{"id": int(row["game_id"]), "label": _game_label(row)}
		for _, row in season_games.iterrows()
	]
	date_label = (
		pd.to_datetime(selected_game["start_date"]).strftime("%B %d, %Y").replace(" 0", " ")
		if pd.notna(selected_game["start_date"])
		else f"Week {int(selected_game['week'])}"
		if pd.notna(selected_game["week"])
		else "Date unavailable"
	)

	unit = request.args.get("unit", "Penn State offense")
	if unit not in ("Penn State offense", "Penn State defense"):
		unit = "Penn State offense"
	quarter = request.args.get("quarter", "All quarters")

	try:
		plays = db.load_game_plays(selected_game_id).reindex(
			columns=[*PLAY_COLUMNS, "play_id"]
		)
	except RuntimeError as error:
		app.logger.exception("Could not load play-by-play from TiDB")
		return render_template(
			"index.html",
			page_error=str(error),
			games_available=True,
		), 503

	unit_plays = plays.loc[plays["unit"].eq(unit)].copy()
	quarter_options = [
		value for value in QUARTER_ORDER if value in unit_plays["quarter"].unique()
	]
	quarter_options.extend(
		sorted(
			value
			for value in unit_plays["quarter"].dropna().unique()
			if value not in quarter_options and value != "Unknown"
		)
	)
	if quarter not in quarter_options and quarter != "All quarters":
		quarter = "All quarters"
	filtered_plays = (
		unit_plays
		if quarter == "All quarters"
		else unit_plays.loc[unit_plays["quarter"].eq(quarter)].copy()
	)

	run_pass = filtered_plays.loc[
		filtered_plays["play_kind"].isin(["Rush", "Pass"])
	]
	stats = {
		"total_plays": f"{len(filtered_plays):,}",
		"rush_share": _fmt_percent(
			float(run_pass["play_kind"].eq("Rush").mean())
			if not run_pass.empty
			else None
		),
		"average_yards": _fmt_number(_mean_or_none(filtered_plays["yards_gained"])),
		"success_rate": _fmt_percent(_mean_or_none(filtered_plays["success"])),
		"average_ppa": _fmt_number(
			_mean_or_none(filtered_plays["play_value_ppa"]), 2
		),
	}

	state_summary = (
		filtered_plays.loc[filtered_plays["score_state"].ne("Unknown")]
		.groupby(["quarter", "score_state"], observed=True)
		.agg(
			plays=("play_id", "count"),
			average_yards=("yards_gained", "mean"),
			success_rate=("success", "mean"),
			average_ppa=("play_value_ppa", "mean"),
		)
		.reset_index()
		.rename(
			columns={
				"quarter": "Quarter",
				"score_state": "Penn State score before play",
				"plays": "Plays",
				"average_yards": "Average yards",
				"success_rate": "Success rate",
				"average_ppa": "Average play value (PPA)",
			}
		)
	)
	state_rows = (
		state_summary.astype(object)
		.where(pd.notna(state_summary), None)
		.to_dict("records")
	)
	play_rows = (
		filtered_plays[PLAY_COLUMNS]
		.sort_values(["quarter", "down"], na_position="last")
		.astype(object)
		.where(pd.notna(filtered_plays[PLAY_COLUMNS]), None)
		.to_dict("records")
	)

	return render_template(
		"index.html",
		games_available=True,
		games_count=len(games),
		seasons_count=len(seasons),
		seasons=seasons,
		selected_season=selected_season,
		game_options=game_options,
		selected_game_id=selected_game_id,
		selected_game=selected_game,
		date_label=date_label,
		unit=unit,
		quarter=quarter,
		quarter_options=quarter_options,
		stats=stats,
		chart_data=_chart_data(filtered_plays) if not filtered_plays.empty else None,
		state_rows=state_rows,
		play_rows=play_rows,
	)


@app.get("/download.csv")
def download_csv():
	game_id = request.args.get("game_id", type=int)
	if game_id is None:
		abort(400, description="Choose a game before downloading plays.")

	unit = request.args.get("unit", "Penn State offense")
	if unit not in ("Penn State offense", "Penn State defense"):
		abort(400, description="Choose a valid side of the ball.")

	try:
		plays = db.load_game_plays(game_id).reindex(
			columns=[*PLAY_COLUMNS, "play_id"]
		)
	except RuntimeError as error:
		app.logger.exception("Could not load plays for CSV download")
		return str(error), 503

	plays = plays.loc[plays["unit"].eq(unit)].copy()
	quarter = request.args.get("quarter", "All quarters")
	if quarter != "All quarters":
		plays = plays.loc[plays["quarter"].eq(quarter)]
	csv_data = plays[PLAY_COLUMNS].to_csv(index=False)
	return Response(
		csv_data,
		mimetype="text/csv",
		headers={
			"Content-Disposition": f"attachment; filename=penn-state-{game_id}-plays.csv"
		},
	)


if __name__ == "__main__":
	app.run(debug=True)
