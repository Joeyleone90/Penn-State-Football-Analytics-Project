# Penn State Game Explorer

An interactive Flask website for reviewing Penn State games, quarter-by-quarter
play calling, and offensive/defensive performance. It stores game results and
play-by-play data in the project's TiDB Cloud database and can be deployed to
Vercel.

## Run locally

1. Install Python 3.10 or newer and the project packages:

   ```powershell
   python -m pip install -r requirements.txt
   ```

2. Set the database password for the website. Locally, the existing `.env` file
   can contain `database-password=...`; on Vercel, configure
   `TIDB_PASSWORD` as an environment variable for each deployment environment.
   Never commit `.env` or put secrets in source code.

3. Start the Flask development server:

   ```powershell
   python -m flask --app main run --debug
   ```

4. Open `http://127.0.0.1:5000`.

## Deploy to Vercel

Import this repository into Vercel and deploy it. Vercel detects the Flask
application in `main.py` automatically. Add `TIDB_PASSWORD` under the project's
Environment Variables, then redeploy. The app uses TiDB's TLS certificate
validation when it connects.

The website only reads data from TiDB. To refresh the database, run the sync
locally instead of exposing a public sync action. Add `api-key=...` to the local
`.env` file (or set `CFBD_API_KEY`) and run, for example:

```powershell
python -c "from sync_data import sync_seasons; print(sync_seasons(list(range(2021, 2026))))"
```

Change the season range as needed. The first sync requests up to 16 endpoints
per selected season (one game list and up to 15 weekly play lists). Repeated
syncs safely update matching game/play IDs rather than adding duplicate rows.

## Data and tables

- `penn_state_games`: completed Penn State game, opponent, date, location,
  final score, and result.
- `penn_state_game_plays`: per-play data for both Penn State offense and
  opponent plays against Penn State, including quarter, score before the play,
  down, distance, yards gained, play type, success, explosive gains, PPA, and
  scoring flag.

The existing `penn_state_plays` table is left in place. The website uses the
new game and full play-by-play tables.

The CFBD play feed supplies yards gained, not air yards; the 15-yard pass-gain
measure is only a long-gain proxy. “Success” is defined as gaining at least 50%
of yards-to-go on first down, 70% on second down, and the line to gain on
third/fourth down. Score state means the score before the snap. These are
descriptive comparisons, not proof that the score caused a coaching decision.
API access and rate limits depend on CollegeFootballData and your account.

## Security

Never commit `.env`, paste its contents into chat, or put keys in source code.
Use TiDB's TLS certificate validation.
