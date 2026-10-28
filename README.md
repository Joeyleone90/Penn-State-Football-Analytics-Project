# Penn State Game Explorer

An interactive Streamlit website for reviewing Penn State games, quarter-by-quarter
play calling, and offensive/defensive performance. It stores game results and
play-by-play data in the project's TiDB Cloud database.

## Start the website

1. Install Python 3.10 or newer.
2. Install the listed packages from a terminal in this folder:

   ```powershell
   python -m pip install -r requirements.txt
   ```

3. Make sure the local `.env` file contains the two secret values:

   ```text
   database-password=YOUR_TIDB_PASSWORD
   api-key=YOUR_COLLEGEFOOTBALLDATA_KEY
   ```

   Replace the examples with your own values. Do not commit or share `.env`.
   The app reads it locally and does not display the values.

4. Start the site:

   ```powershell
   python -m streamlit run main.py
   ```

5. Open the local URL Streamlit prints, usually `http://localhost:8501`.
6. If the database has no game details yet, expand **Update data from
   CollegeFootballData** in the sidebar, choose seasons, and click **Sync
   selected seasons**. The first sync requests up to 16 endpoints per selected
   season (one game list and up to 15 weekly play lists). Repeated syncs safely
   update matching game/play IDs rather than adding duplicate rows.

## Data and tables

- `penn_state_games`: completed Penn State game, opponent, date, location,
  final score, and result.
- `penn_state_game_plays`: per-play data for both Penn State offense and
  opponent plays against Penn State, including quarter, score before the play,
  down, distance, yards gained, play type, success, explosive gains, PPA, and
  scoring flag.

The existing `penn_state_plays` table is left in place. The website uses the
new game and full play-by-play tables.

The CFBD play feed supplies yards gained, not air yards; the dashboard's
15-yard pass-gain measure is only a long-gain proxy. “Success” is defined as
gaining at least 50% of yards-to-go on first down, 70% on second down, and the
line to gain on third/fourth down. Score state means the score before the snap.
These are descriptive comparisons, not proof that the score caused a coaching
decision. API access and rate limits depend on CollegeFootballData and your
account.

## Security

Never commit `.env`, paste its contents into chat, or put keys in source code.
Use TiDB's TLS certificate validation. Because the CollegeFootballData key was
displayed in a shared conversation, revoke it and create a replacement before
continuing to use the app.
