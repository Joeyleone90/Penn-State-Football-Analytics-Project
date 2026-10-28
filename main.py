"""Streamlit site for exploring Penn State football games and play-by-play."""

import pandas as pd
import plotly.express as px
import streamlit as st

import db
from sync_data import sync_seasons


QUARTER_ORDER = ["Q1", "Q2", "Q3", "Q4", "OT1", "OT2", "OT3", "OT4"]
COLORS = {"Rush": "#1b5e3b", "Pass": "#c99a2e", "Other": "#7f8c8d"}


def _mean_or_none(values: pd.Series):
	values = pd.to_numeric(values, errors="coerce").dropna()
	return float(values.mean()) if not values.empty else None


def _fmt_number(value, digits: int = 1) -> str:
	return f"{value:.{digits}f}" if value is not None and pd.notna(value) else "N/A"


def _fmt_percent(value) -> str:
	return f"{value:.1%}" if value is not None and pd.notna(value) else "N/A"


def _render_game(plays: pd.DataFrame, game: pd.Series) -> None:
	date_label = (
		pd.to_datetime(game["start_date"]).strftime("%B %d, %Y").replace(" 0", " ")
		if pd.notna(game["start_date"])
		else f"Week {int(game['week'])}"
	)
	st.header(f"Penn State vs. {game['opponent']}")
	st.caption(
		f"{int(game['season'])} · {date_label} · {game['location']} · "
		f"Final: Penn State {int(game['penn_state_points'])}, "
		f"{game['opponent']} {int(game['opponent_points'])} · {game['result']}"
	)

	if plays.empty:
		st.info("No play-by-play is stored for this game yet. Use **Sync data** in the sidebar.")
		return

	unit = st.selectbox(
		"Choose the side of the ball",
		["Penn State offense", "Penn State defense"],
		help="Offense shows Penn State's plays. Defense shows opposing offensive plays against Penn State.",
	)
	unit_plays = plays.loc[plays["unit"].eq(unit)].copy()
	if unit_plays.empty:
		st.warning(f"There are no {unit.lower()} plays for this game.")
		return

	quarter_options = [
		quarter for quarter in QUARTER_ORDER if quarter in unit_plays["quarter"].unique()
	]
	quarter_options.extend(
		sorted(
			quarter
			for quarter in unit_plays["quarter"].dropna().unique()
			if quarter not in quarter_options and quarter != "Unknown"
		)
	)
	quarter = st.selectbox("Quarter", ["All quarters", *quarter_options])
	if quarter != "All quarters":
		unit_plays = unit_plays.loc[unit_plays["quarter"].eq(quarter)].copy()

	run_pass = unit_plays.loc[unit_plays["play_kind"].isin(["Rush", "Pass"])].copy()
	total_plays = len(unit_plays)
	rush_share = (
		float(run_pass["play_kind"].eq("Rush").mean()) if not run_pass.empty else None
	)
	average_yards = _mean_or_none(unit_plays["yards_gained"])
	success_rate = _mean_or_none(unit_plays["success"])
	epa = _mean_or_none(unit_plays["play_value_ppa"])
	explosive_rate = _mean_or_none(
		unit_plays.loc[unit_plays["play_kind"].eq("Pass"), "explosive_pass_15_plus"]
	)

	first, second, third, fourth, fifth = st.columns(5)
	first.metric("Plays", f"{total_plays:,}")
	second.metric("Rush share", _fmt_percent(rush_share))
	third.metric("Avg. yards/play", _fmt_number(average_yards))
	fourth.metric("Success rate", _fmt_percent(success_rate))
	fifth.metric("Avg. play value (PPA)", _fmt_number(epa, 2))
	st.caption(
		"Success: 50% of yards-to-go on first down, 70% on second, and the line "
		"to gain on third/fourth. Explosive pass = 15+ yards gained (not air yards)."
	)

	left, right = st.columns(2)
	with left:
		st.subheader("Play type by quarter")
		mix = (
			unit_plays.groupby(["quarter", "play_kind"], observed=True)
			.size()
			.rename("plays")
			.reset_index()
		)
		if mix.empty:
			st.info("There are no categorized plays to chart.")
		else:
			fig = px.bar(
				mix,
				x="quarter",
				y="plays",
				color="play_kind",
				barmode="stack",
				color_discrete_map=COLORS,
				labels={"quarter": "Quarter", "plays": "Number of plays", "play_kind": "Play type"},
			)
			fig.update_layout(height=370, margin={"l": 8, "r": 8, "t": 20, "b": 8})
			st.plotly_chart(fig, width="stretch")

	with right:
		st.subheader("Average yards gained by quarter")
		yards = (
			unit_plays.groupby(["quarter", "play_kind"], observed=True)
			.agg(average_yards=("yards_gained", "mean"), plays=("yards_gained", "count"))
			.reset_index()
		)
		if yards.empty:
			st.info("Yardage is not available for this selection.")
		else:
			fig = px.line(
				yards,
				x="quarter",
				y="average_yards",
				color="play_kind",
				markers=True,
				hover_data=["plays"],
				color_discrete_map=COLORS,
				labels={
					"quarter": "Quarter",
					"average_yards": "Average yards",
					"play_kind": "Play type",
					"plays": "Plays with yardage",
				},
			)
			fig.update_layout(height=370, margin={"l": 8, "r": 8, "t": 20, "b": 8})
			st.plotly_chart(fig, width="stretch")

	st.subheader("Performance by score situation")
	state_summary = (
		unit_plays.loc[unit_plays["score_state"].ne("Unknown")]
		.groupby(["quarter", "score_state"], observed=True)
		.agg(
			plays=("play_id", "count"),
			average_yards=("yards_gained", "mean"),
			success_rate=("success", "mean"),
			average_ppa=("play_value_ppa", "mean"),
		)
		.reset_index()
	)
	if state_summary.empty:
		st.info("Score-situation data is not available for this game.")
	else:
		state_summary = state_summary.rename(
			columns={
				"quarter": "Quarter",
				"score_state": "Penn State score before play",
				"plays": "Plays",
				"average_yards": "Average yards",
				"success_rate": "Success rate",
				"average_ppa": "Average play value (PPA)",
			}
		)
		st.dataframe(state_summary, hide_index=True, width="stretch")

	with st.expander("Inspect the individual plays"):
		display_columns = [
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
		st.dataframe(
			unit_plays[display_columns].sort_values(
				["quarter", "down"], na_position="last"
			),
			hide_index=True,
			width="stretch",
		)
		st.download_button(
			"Download this game's filtered plays",
			unit_plays[display_columns].to_csv(index=False).encode("utf-8"),
			file_name=f"penn-state-{int(game['game_id'])}-plays.csv",
			mime="text/csv",
		)


def main() -> None:
	st.set_page_config(
		page_title="Penn State Game Explorer",
		page_icon="🏈",
		layout="wide",
	)
	st.title("Penn State Game Explorer")
	st.write(
		"Explore game-by-game play-calling and performance by quarter, score "
		"situation, down, and side of the ball."
	)

	with st.sidebar:
		st.header("Controls")
		with st.expander("Update data from CollegeFootballData", expanded=False):
			st.write(
				"Sync downloads game results and weekly play-by-play for the "
				"selected seasons, then updates the TiDB project tables."
			)
			season_range = st.select_slider(
				"Seasons to sync",
				options=list(range(2015, 2027)),
				value=(2021, 2025),
			)
			if st.button("Sync selected seasons", type="primary", width="stretch"):
				seasons = list(range(season_range[0], season_range[1] + 1))
				try:
					with st.spinner(
						f"Downloading and saving {season_range[0]}–{season_range[1]}..."
					):
						result = sync_seasons(seasons)
					st.cache_data.clear()
					st.success(
						f"Synced {result['games_synced']:,} games and "
						f"{result['plays_fetched']:,} plays."
					)
				except (RuntimeError, ValueError) as error:
					st.error(str(error))

	try:
		with st.spinner("Loading games from TiDB..."):
			games = db.load_games()
	except RuntimeError as error:
		st.error(str(error))
		st.info(
			"Check that the project `.env` file contains the database password, "
			"then refresh the page. Use the sync panel after the app connects."
		)
		st.stop()

	if games.empty:
		st.warning("No completed Penn State games are in TiDB yet.")
		st.info("Open **Update data from CollegeFootballData** in the sidebar and sync seasons.")
		st.stop()

	seasons = sorted(games["season"].dropna().astype(int).unique().tolist())
	selected_season = st.sidebar.selectbox(
		"Season to explore", seasons, index=len(seasons) - 1
	)
	season_games = games.loc[games["season"].eq(selected_season)].copy()
	season_games["display_label"] = season_games.apply(
		lambda row: (
			f"Week {int(row['week']) if pd.notna(row['week']) else '?'} · "
			f"{row['opponent']} · {row['result']} "
			f"({int(row['penn_state_points'])}-{int(row['opponent_points'])})"
		),
		axis=1,
	)
	selected_label = st.selectbox("Choose a game", season_games["display_label"].tolist())
	selected_game = season_games.loc[
		season_games["display_label"].eq(selected_label)
	].iloc[0]

	st.caption(
		f"TiDB contains {len(games):,} completed games across {len(seasons)} "
		f"seasons. Game details below come from stored play-by-play records."
	)
	try:
		with st.spinner("Loading the selected game's play-by-play..."):
			plays = db.load_game_plays(int(selected_game["game_id"]))
	except RuntimeError as error:
		st.error(str(error))
		st.stop()

	_render_game(plays, selected_game)


if __name__ == "__main__":
	main()
