# Install

## Clone the Repository

<div id="code-block">
    <div class="tab flex space-x-4 border-b border-gray-700 mb-2">
        <button class="tablinks px-4 py-2 text-gray-400 hover:text-white transition-colors duration-200 focus:outline-none"
                onclick="openTab(event, 'Windows')"
                id="defaultOpen">
            Windows
        </button>
        <button class="tablinks px-4 py-2 text-gray-400 hover:text-white transition-colors duration-200 focus:outline-none"
                onclick="openTab(event, 'Mac')">
            Mac
        </button>
        <button class="tablinks px-4 py-2 text-gray-400 hover:text-white transition-colors duration-200 focus:outline-none"
                onclick="openTab(event, 'Linux')">
            Linux
        </button>
    </div>

    <div id="Windows" class="tabcontent hidden bg-gray-900 text-white py-1 px-4 rounded-lg border border-gray-800">
        <pre class="bg-gray-800 text-sm text-gray-200 py-2 px-4 rounded-lg overflow-x-auto">
            <code class="language-bash">
git clone https://github.com/sousa-dev/djast.git
cd djast
python setup.py
            </code>
        </pre>
    </div>

    <div id="Mac" class="tabcontent hidden bg-gray-900 text-white py-1 px-4 rounded-lg border border-gray-800">
        <pre class="bg-gray-800 text-sm text-gray-200 py-2 px-4 rounded-lg overflow-x-auto">
            <code class="language-bash">
git clone https://github.com/sousa-dev/djast.git
cd djast
python3 setup.py
            </code>
        </pre>
    </div>

    <div id="Linux" class="tabcontent hidden bg-gray-900 text-white py-1 px-4 rounded-lg border border-gray-800">
        <pre class="bg-gray-800 text-sm text-gray-200 py-2 px-4 rounded-lg overflow-x-auto">
            <code class="language-bash">
git clone https://github.com/sousa-dev/djast.git
cd djast
python3 setup.py
            </code>
        </pre>
    </div>
</div>

## What `setup.py` Does

The setup script (run from the **repo root**, not `src/`):

1. Creates a `.venv/` virtual environment.
2. Installs Python dependencies from `src/requirements.txt`.
3. Runs initial database migrations.

## Configure Environment Variables

<div id="code-block">
    <div class="tab flex space-x-4 border-b border-gray-700 mb-2">
        <button class="tablinks px-4 py-2 text-gray-400 hover:text-white transition-colors duration-200 focus:outline-none"
                onclick="openTab(event, 'Windows')"
                id="defaultOpen">
            Windows
        </button>
        <button class="tablinks px-4 py-2 text-gray-400 hover:text-white transition-colors duration-200 focus:outline-none"
                onclick="openTab(event, 'Mac')">
            Mac
        </button>
        <button class="tablinks px-4 py-2 text-gray-400 hover:text-white transition-colors duration-200 focus:outline-none"
                onclick="openTab(event, 'Linux')">
            Linux
        </button>
    </div>

    <div id="Windows" class="tabcontent hidden bg-gray-900 text-white py-1 px-4 rounded-lg border border-gray-800">
        <pre class="bg-gray-800 text-sm text-gray-200 py-2 px-4 rounded-lg overflow-x-auto">
            <code class="language-bash">
copy src\src\.env.example src\src\.env
            </code>
        </pre>
    </div>

    <div id="Mac" class="tabcontent hidden bg-gray-900 text-white py-1 px-4 rounded-lg border border-gray-800">
        <pre class="bg-gray-800 text-sm text-gray-200 py-2 px-4 rounded-lg overflow-x-auto">
            <code class="language-bash">
cp src/src/.env.example src/src/.env
            </code>
        </pre>
    </div>

    <div id="Linux" class="tabcontent hidden bg-gray-900 text-white py-1 px-4 rounded-lg border border-gray-800">
        <pre class="bg-gray-800 text-sm text-gray-200 py-2 px-4 rounded-lg overflow-x-auto">
            <code class="language-bash">
cp src/src/.env.example src/src/.env
            </code>
        </pre>
    </div>
</div>

Edit `src/src/.env` and set at minimum:

- `SECRET_KEY` — generate one at [/tools/django-secret-key-generator/](/tools/django-secret-key-generator/)
- `DEBUG=True` for local development

See [Environment](/docs/get_started/environment) for the full variable list.

## Verify Installation

```bash
cd src
python manage.py check
```

If this prints no errors, you're ready for [First Run](/docs/get_started/first_run).
