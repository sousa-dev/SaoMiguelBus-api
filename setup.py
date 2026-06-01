import os
if os.name != 'nt':
    import subprocess
    import sys
    import time

    def check_and_install_venv():
        try:
            # Check if venv is installed by trying to import it
            import venv
            print("venv is already installed.")
        except ImportError:
            print("venv is not installed. Attempting to install...")
            subprocess.check_call([sys.executable, '-m', 'pip', 'install', 'virtualenv'])
            try:
                # Check again after installation
                import venv
                print("venv has been successfully installed.")
            except ImportError:
                print("Failed to install venv. Please install it manually")
                sys.exit(1)

    # Check if 'python' or 'python3' should be used
    python_command = 'python' if os.system('python --version > /dev/null 2>&1') == 0 else 'python3'
    if os.system('python --version > /dev/null 2>&1') != 0 and os.system('python3 --version > /dev/null 2>&1') != 0:
        print('Python is not installed. Please install Python and try again.')
        exit(1)
        
    check_and_install_venv()

    def print_and_sleep(message, sleep_time=0.75):
        print(message)
        time.sleep(sleep_time)

    # Create virtual environment
    print_and_sleep('Creating virtual environment...')
    os.system(f'{python_command} -m venv .venv')

    # Ensure pip is installed and up-to-date
    print_and_sleep('Ensuring pip is installed and up-to-date...')
    ensurepip_result = subprocess.call(f'bash -c "source .venv/bin/activate && {python_command} -m ensurepip"', shell=True)
    upgrade_pip_result = subprocess.call(f'bash -c "source .venv/bin/activate && pip install --upgrade pip"', shell=True)

    if ensurepip_result != 0:
        print('Failed to run ensurepip. Please check your Python installation.')
        exit(1)

    if upgrade_pip_result != 0:
        print('Failed to upgrade pip. Please check your network connection and try again.')
        exit(1)
    print('pip is installed and up-to-date.')

    # Install requirements
    print_and_sleep('Installing requirements...')
    subprocess.call(f'bash -c "source .venv/bin/activate && pip install -r src/requirements.txt"', shell=True)
        
    # Run the migrations
    print_and_sleep('Running migrations...')
    subprocess.call(f'bash -c "source .venv/bin/activate && python src/manage.py makemigrations"', shell=True)
    subprocess.call(f'bash -c "source .venv/bin/activate && python src/manage.py migrate"', shell=True)

    print('Setup completed successfully!')
    
else:
    import os
    import subprocess
    import sys
    import time
    import venv

    def check_and_install_venv():
        try:
            # Check if venv is available
            import venv
            print("venv is already available.")
        except ImportError:
            print("venv is not available in your Python installation.")
            sys.exit(1)

    def run_command(command, shell=False):
        result = subprocess.run(command, shell=shell, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        if result.returncode != 0:
            print(f"Command failed: {command}")
            print(result.stderr.decode())
            sys.exit(1)
        return result.stdout.decode()

    def print_and_sleep(message, sleep_time=0.75):
        print(message)
        time.sleep(sleep_time)

    check_and_install_venv()

    # Determine which Python command to use
    python_command = sys.executable

    # Create virtual environment
    print_and_sleep('Creating virtual environment...')
    venv_dir = '.venv'
    venv.create(venv_dir, with_pip=True)

    # Ensure pip is installed and up-to-date
    print_and_sleep('Ensuring pip is installed and up-to-date...')

    # Activate and update pip on Windows
    activate_script = os.path.join(venv_dir, 'Scripts', 'activate.bat')
    run_command(f'{activate_script} && {python_command} -m ensurepip', shell=True)
    run_command(f'{activate_script} && pip install --upgrade pip', shell=True)

    print('pip is installed and up-to-date.')

    # Install requirements
    print_and_sleep('Installing requirements...')
    requirements_file = os.path.join('src', 'requirements.txt')

    run_command(f'{activate_script} && pip install -r {requirements_file}', shell=True)

    # Run the migrations
    print_and_sleep('Running migrations...')
    manage_py = os.path.join('src', 'manage.py')

    run_command(f'{activate_script} && python {manage_py} makemigrations', shell=True)
    run_command(f'{activate_script} && python {manage_py} migrate', shell=True)


    print('Setup completed successfully!')