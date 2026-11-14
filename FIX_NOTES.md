# Fix: "No module named pip / uvicorn" when starting

The Python environment in %LOCALAPPDATA%\RouteNexVenv was empty or broken (project, database and admin login are unaffected).
Quick fix now:  setup.bat  (rebuilds the environment, 2-3 minutes, needs internet), then start.bat.
Copy `start.bat` and `setup.bat` from this zip over yours: start.bat now repairs missing packages itself, or calls setup.bat if the environment is broken; setup.bat now also runs ensurepip.
