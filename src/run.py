import os
if os.name != 'nt':
    import signal
    import subprocess
    import threading
    import time

    def verify_root_directory():
        expected_files = ['manage.py', 'run.py']
        for filename in expected_files:
            if not os.path.isfile(filename):
                raise Exception(f"Please run the script from the root directory of your Django project [djast/src/].")

    verify_root_directory()

    def run_command(command):
        result = subprocess.run(command, shell=True, capture_output=True, text=True, executable='/bin/bash')
        if result.returncode != 0:
            print(f"Error running command: {command}")
            print(result.stderr)
            print("Exiting...")
            exit(1)
        else:
            print(result.stdout)

    def run_command_continuous(command, start_event=None):
        process = subprocess.Popen(command, shell=True, preexec_fn=os.setsid, executable='/bin/bash')
        if start_event:
            start_event.set()  # Signal that the process has started
        try:
            process.wait()
        except KeyboardInterrupt:
            os.killpg(os.getpgid(process.pid), signal.SIGTERM)

    # Check if 'python' or 'python3' should be used
    python_command = 'python' if os.system('python --version > /dev/null 2>&1') == 0 else 'python3'
    if os.system('python --version > /dev/null 2>&1') != 0 and os.system('python3 --version > /dev/null 2>&1') != 0:
        raise Exception('Python is not installed. Please install Python and try again.')
        exit(1)

    # Source virtual environment
    source_venv = 'source ../.venv/bin/activate'

    # Run Django management commands
    commands = [
        f'{source_venv} && {python_command} manage.py makemigrations',
        f'{source_venv} && {python_command} manage.py migrate',
        f'{source_venv} && {python_command} manage.py tailwind install',
        f'{source_venv} && {python_command} manage.py collectstatic --noinput'
    ]

    for command in commands:
        print(f"$ {command}")
        run_command(command)

    # Event to signal that tailwind has started
    tailwind_started_event = threading.Event()

    # Run tailwind start and wait for it to signal that it has started
    tailwind_process = subprocess.Popen(f'bash -c "{source_venv} && {python_command} manage.py tailwind start"', shell=True, preexec_fn=os.setsid)

    tailwind_started_event.set()

    # Wait for tailwind to start before running the server
    time.sleep(5)

    # Run the Django server
    runserver_process = subprocess.Popen(f'bash -c "{source_venv} && {python_command} manage.py runserver"', shell=True, preexec_fn=os.setsid)

    try:
        tailwind_process.wait()
        runserver_process.wait()
    except KeyboardInterrupt:
        print("Terminating processes...")
        os.killpg(os.getpgid(tailwind_process.pid), signal.SIGTERM)
        os.killpg(os.getpgid(runserver_process.pid), signal.SIGTERM)
else:
    import subprocess
    import sys
    import threading
    import time
    import signal

    def verify_root_directory():
        expected_files = ['manage.py', 'run.py']
        for filename in expected_files:
            if not os.path.isfile(filename):
                raise Exception(f"Please run the script from the root directory of your Django project [djast/src/].")

    verify_root_directory()

    def run_command(command, shell=False):
        result = subprocess.run(command, shell=shell, capture_output=True, text=True)
        if result.returncode != 0:
            print(f"Error running command: {command}")
            print(result.stderr)
            print("Exiting...")
            sys.exit(1)
        else:
            print(result.stdout)

    def run_command_in_env(activate_script, command):
        full_command = f'cmd.exe /c "{activate_script} & {command}"'
        run_command(full_command, shell=True)

    # Check if 'python' or 'python3' should be used
    python_command = '..\\.venv\\Scripts\\python.exe'

    # Source virtual environment
    activate_script = '..\\.venv\\Scripts\\activate.bat'

    # Run Django management commands in virtual environment
    commands = [
        f'{python_command} manage.py makemigrations',
        f'{python_command} manage.py migrate',
        f'{python_command} manage.py tailwind install',
        f'{python_command} manage.py collectstatic --noinput'
    ]

    for command in commands:
        print(f"$ {command}")
        run_command_in_env(activate_script, command)

    # Event to signal that tailwind has started
    tailwind_started_event = threading.Event()

    # Run tailwind start
    tailwind_command = f'{python_command} manage.py tailwind start'

    tailwind_process = subprocess.Popen(
        f'cmd.exe /c "{activate_script} & {tailwind_command}"',
        shell=True
    )
    tailwind_started_event.set()

    # Wait for tailwind to start before running the server
    time.sleep(5)

    # Run the Django server
    runserver_command = f'{python_command} manage.py runserver'

    runserver_process = subprocess.Popen(
        f'cmd.exe /c "{activate_script} & {runserver_command}"',
        shell=True
    )

    try:
        tailwind_process.wait()
        runserver_process.wait()
    except KeyboardInterrupt:
        print("Terminating processes...")
        tailwind_process.terminate()
        runserver_process.terminate()