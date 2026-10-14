# Demo guide: ACME Project Tracker on LocalStack

A rehearsed, 10-minute demo (with a 5-minute cut) that runs on LocalStack, a local copy of AWS. Every step below was
run in a real browser and passes. The demo data is loaded by one command and dated relative to today, so the story
is the same on any day.

```
browser :3000 (React) --> proxy :3001 --> Lambda (FastAPI, in LocalStack/Docker) --> PostgreSQL (Docker, 172.17.0.1:5432)
```

## 1. Get ready (30 minutes before)

```sh
docker ps --format '{{.Names}}'     # expect: localstack-main, pm-demo-postgres, and a ...lambda-coding-workshop-pm-api... container
```

If any is missing (after a reboot, or LocalStack was restarted), start everything again (about 3 minutes):

```sh
./bin/demo-postgres.sh      # PostgreSQL 17 in Docker, reachable from the Lambda container; no sudo
./bin/start-dev.sh          # LocalStack, deploys the API with Terraform, proxy, then the website (leave it running)
```

Then, every time before you present or practise:

```sh
./bin/demo-ready.sh         # about 5 seconds: empties the database, loads the sample company, sets the logins below
```

Finally open http://localhost:3000, sign in as `admin1` once and sign out. That starts the API container, which
is slow on its first request (up to a minute), so it never happens in front of people.

Window at 1280 px wide and 100% zoom. Close chat and mail notifications. Have this page open on a second screen.

## 2. The accounts

| Username | Password | Who | Used for |
|---|---|---|---|
| `admin1` | `Demo1234!` | System Admin (admin) | Company view, archive and restore |
| `maria1` | `Demo1234!` | Maria Lopez (manager) | Website Redesign: assign, tick, complete |
| `james1` | `Demo1234!` | James Carter (manager) | The overdue and at-risk projects |
| `alex01` | `Demo1234!` | Alex Kim (employee) | "My work", no money shown |
| `nina01` | `Welcome123!` | Nina Park (new hire) | First sign-in forces a new password (works once) |
| `priya1` `sofia1` `tom001` `lena01` `omar01` | `Demo1234!` | More employees | Not needed in the script |

The company: two managers, seven employees, four projects.

| Project | Manager | State | Why |
|---|---|---|---|
| Mobile App Launch | James | **Overdue** | The end date has passed and both milestones are late |
| Data Platform Migration | James | **At risk** | Spending is far ahead of the calendar, and the planned staffing costs more than the budget |
| Website Redesign | Maria | On track | About two thirds of the time used, a bit over a third of the budget |
| Customer Portal | Maria | On track (planned) | Starts in two weeks |

## 3. The script

Say the one-line idea first: **"We replaced timesheets with a calendar, so the system always knows who is on what, what it
costs, and whether it is late."**

### Act 1. The company at a glance (admin, 2 min)

1. Sign in as `admin1` / `Demo1234!`. You land on the **Dashboard**.
2. Point at the four tiles, then at the project list. **Say:** "Ranked by urgency: overdue first, then at risk. Each project
   says why, in words."
3. Point at one pulse bar. **Say:** "The fill is work done, the dark marker is today. Fill behind the marker means behind schedule."
4. Click **Data Platform Migration**. Read the box "Why this project is at risk": spending is ahead of the calendar, and the planned
   staffing will cost more than the budget. **Say:** "Notice the work is actually ahead of the calendar here. The money is
   going faster, and the system caught it. Nobody set this status; it is calculated from dates and assignments."
5. Click the **Team** tab. **Say:** "Nobody types hours. Every Monday to Friday on a milestone is an 8-hour shift, so hours and cost
   come from the calendar."
6. Sign out (icon, top right).

### Act 2. What an employee sees (1 min)

1. Sign in as `alex01` / `Demo1234!`. You land on **My work**.
2. **Say:** "Alex sees today's milestone, hours this week out of 40, and deliverable progress. Alex never sees a dollar."
   Click the project: only Alex's project is visible, and no money appears.
3. Sign out.

### Act 3. A manager at work (maria1, 4 min)

1. Sign in as `maria1` / `Demo1234!`. **Say:** "Maria sees only her two projects, not James's."
2. Open **Website Redesign**. Scroll to the **Launch** milestone (nobody is assigned).
3. Click **Assign a person**, choose **Sofia Rossi**, leave the dates empty, click **Assign**.
   - **You see:** a red message: *Sofia Rossi is already on milestone 'Discovery' of 'Customer Portal' from ... to ...*
   - **Say:** "One person, one milestone per day, even across projects. The server refuses and names the clash. That makes
     over-allocation impossible, not just reported."
4. Cancel, click **Assign a person** again, choose **Priya Shah**, click **Assign**. Priya appears in the team.
5. In the **Build** milestone click **Complete milestone**, then **Sign off and complete** (leave the note empty).
   - **You see:** *1 deliverable(s) are not done yet: Dashboard*
   - **Say:** "A milestone is signed off only after the manager has reviewed every deliverable."
6. Cancel. Tick the **Dashboard** checkbox. Click **Complete milestone**, type a note such as
   *Reviewed with the client; both screens signed off*, click **Sign off and complete**.
   - **You see:** Build leaves the list, and the Milestones tile reads **2 of 3**.
   - **Say:** "It moved to the archive but still counts toward progress, and Alex is free from tomorrow."
7. Sign out.

### Act 4. A new hire (1 min)

1. Sign in as `nina01` / `Welcome123!`. You are sent to **Choose a new password**.
2. **Say:** "Generated passwords work once. Nina must choose her own before she sees anything."
   Enter the current password, a new one such as `Welcome456!` twice, click **Save new password**. She lands on **My work**
   with no milestone yet.
3. Sign out.

### Act 5. Nothing is ever deleted (admin, 1.5 min)

1. Sign in as `admin1`. Open **Website Redesign**.
2. **Say:** "Admins still see the milestone Maria completed, marked *Completed, archived*, with her review note. Managers and
   employees no longer do."
3. Go to **Projects**, open **Customer Portal**, click **Archive**, confirm. Open **Archive** in the menu: it is listed.
4. Click **Restore**. **Say:** "There is no delete anywhere in the API; a test proves it. Archive, then restore."

### Close (30 seconds)

"The API behind this passes 154 tests and a 138-request Postman run with no failures, both locally and on LocalStack.
What is left: the AWS deployment, and growing this demo UI into the full app."

### 5-minute cut

Act 1 (steps 1 to 4), Act 3 steps 3, 5 and 6 only, then Act 5 steps 3 and 4.

## 4. After each run

```sh
./bin/demo-ready.sh         # puts everything back, including Maria's completed milestone and Nina's password
```

## 5. If something goes wrong

| What you see | What to do |
|---|---|
| First click after a pause is slow | The API container is waking up. Wait, then continue. Avoid it by signing in once beforehand |
| "Cannot reach the server" | `curl http://localhost:3001/api/pm-api/health`. If there is no answer, run `./bin/start-dev.sh` (3 minutes) |
| A login is refused, or the data looks wrong | `./bin/demo-ready.sh` (5 seconds) |
| The site does not load at all | `./bin/start-dev.sh` restarts the proxy and website |
| LocalStack was restarted or the machine rebooted | `./bin/demo-postgres.sh`, `./bin/start-dev.sh`, then `./bin/demo-ready.sh` |
| The browser offers to save a password | Dismiss it |
| Everything fails on stage | Walk through `docs/demo-screenshots/` (one picture per step), then show the saved responses in the Postman collection |

## 6. Other commands

| Command | What it does |
|---|---|
| `./bin/demo-reset.sh` | Empties all data (first admin only, `admin1` / `ChangeMe123!`, forced password change) |
| `./bin/demo-postgres.sh --reset` | Throws away the whole database volume |
| `./bin/demo-postgres.sh --stop` | Stops the database container |
| `npx newman run docs/postman/acme-pm-api.postman_collection.json -e docs/postman/localstack.postman_environment.json` | Full API test (run `./bin/demo-reset.sh` first, and `./bin/demo-ready.sh` after). Expect 138 requests, 554 assertions, 0 failures |

## 7. Why it is set up this way

The Lambda container reaches the host at `172.17.0.1`, but the system PostgreSQL listens on `127.0.0.1` only, and changing
that needs `sudo`. The Docker database sits on the Docker bridge instead and leaves the system database untouched.
`start-dev.sh` accepts a database reachable there. The sample company is created through the real API
(`POST /admin/seed-demo`), so the demo data goes through the same rules as real data; only the usernames and passwords
are then set to memorable values by `demo-ready.sh`.
