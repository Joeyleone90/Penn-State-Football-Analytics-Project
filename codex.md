CLAUDE.md
Read this before doing anything in this repo.
The project
I am building a sports analytics website for Penn State Nittany Lions Football.
The person I am building it for is coaches and fans.
I am building this so that they can have a better understanding of penn state's strenghts and weeknesses based on how long the game has progress.
The stack
● Python 3.12
● Flask for the web app
● TiDB Cloud (MySQL-compatible) for the database
● PyMySQL to connect, python-dotenv for config, certifi for TLS
● Plain HTML and CSS in templates. No React, no Tailwind, no build step.
Do not suggest Django, FastAPI, SQLite, Postgres, or an ORM unless I ask.
The structure
.env secrets, never committed, never read by you
.gitignore
CLAUDE.md this file
requirements.txt
etl/load.py pulls data from the source into the database
app/main.py Flask routes, one per page
app/db.py the only file that opens a database connection
app/templates/ HTML pages (Flask requires this exact name)
app/static/ CSS, images, chart scripts (Flask requires this name)
New code goes in one of these. If something does not fit, tell me and we will decide together
where it belongs.
My data
Source: cfbd
** UPDATE THIS AS WE GO CLAUDE **
You have never seen this data. Do not guess column names.
Rules
● Never read, edit, print, or echo .env. If a credential ends up anywhere outside .env,
stop and tell me.
● Explain what you are about to change, and which files, before changing it.
● Prefer the simplest version that works. One file over three. No config systems, no
abstractions, no "for later" code.
● Ask before adding a library to requirements.txt.
● One change at a time. Do not refactor files I did not ask about.
● If you are unsure about the data, the question, or what I meant, ask. Guessing wastes
more of my time than asking does.
● Write code I can read. I am learning. Clear beats clever, always.
How I work
I am a student learning this. When you write something non-obvious, add one short comment
saying why, not what. If I ask what a line does and the answer is complicated, that line is
probably too complicated