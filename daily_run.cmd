@echo off
rem Daily full run, started by Windows Task Scheduler ("QA Job Scraper daily run").
rem Results go to the same database the website reads; the log is output\daily_run.log.
rem Remove the schedule with:  schtasks /Delete /TN "QA Job Scraper daily run" /F
cd /d "%~dp0"
echo ===== %date% %time% ===== >> output\daily_run.log
"C:\Users\Ammar\AppData\Local\Programs\Python\Python311\python.exe" run.py --mode full --quiet --trigger schedule >> output\daily_run.log 2>&1
