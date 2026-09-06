# Getting started with FutureForge

A step by step guide to running FutureForge on your own computer. It assumes no
prior experience with Python. Every command below is something you type into a
terminal window, and after each one there is a note describing what you should
expect to see.

There are two ways to use FutureForge:

1. **In the terminal.** Text only, works on any computer that has Python. This is
   the fastest way to see it working, and it is the one to start with.
2. **As a desktop app.** A real window with colours, buttons and typed answers.
   It needs one extra thing installed on macOS, explained in Part 4.

---

## Part 1: Check that you have Python

FutureForge needs Python version 3.9 or newer. Most Macs and many Linux machines
already have it. To find out, open a terminal.

* **macOS:** press `Command` and `Space`, type `Terminal`, press `Enter`.
* **Windows:** press the Start button, type `PowerShell`, press `Enter`.
* **Linux:** press `Ctrl`, `Alt` and `T` together.

Now type this and press `Enter`:

```bash
python3 --version
```

**What you should see:** something like `Python 3.13.1`. Any number that starts
with 3.9 or higher is fine.

**If you see "command not found"** it means Python is not installed. Go to
[python.org/downloads](https://www.python.org/downloads/), download the installer
for your system, run it, then close and reopen your terminal and try again.

> On Windows, the command is sometimes just `python` instead of `python3`. If
> `python3` does not work, try `python --version`. Wherever this guide says
> `python3`, use whichever one worked for you.

---

## Part 2: Download the project

You can either use Git, or download a ZIP file if you do not have Git.

### Using Git

```bash
git clone https://github.com/Awesomeav23/FutureForge.git
cd FutureForge
```

**What you should see:** a few lines about cloning, then your terminal prompt
changes to show you are inside the `FutureForge` folder.

### Without Git

1. Open <https://github.com/Awesomeav23/FutureForge> in a browser.
2. Click the green **Code** button, then **Download ZIP**.
3. Unzip the downloaded file.
4. In your terminal, type `cd ` (with a space after it), then drag the unzipped
   folder onto the terminal window and press `Enter`.

**What you should see:** your prompt now shows the FutureForge folder.

The `cd` command means "change directory". Every command in the rest of this
guide needs to be run from inside this folder. If you close your terminal and come
back later, you will need to `cd` into it again.

---

## Part 3: Run it in the terminal

This is the quickest way to confirm everything works. There is nothing to install
first. Type:

```bash
python3 -m futureforge.cli --profile examples/sample_student.json --top 5
```

**What you should see:** a report for a made up student named Maya Chen, listing
five careers. The first is Registered Nurse at a 95% match, with a pay range, the
schooling required, and a paragraph explaining why it matched her answers.

That command uses a student profile that ships with the project. There is a second
one for a student interested in trades:

```bash
python3 -m futureforge.cli --profile examples/trades_student.json --top 3
```

**What you should see:** a different set of results, led by Heavy Equipment
Operator, because this student's answers point somewhere else entirely.

### Answering the questions yourself

Leave off the `--profile` part and the program will interview you directly:

```bash
python3 -m futureforge.cli
```

**What you should see:** it asks for your name and grade, then works through the four
questions one at a time. Each question shows a numbered list of options, and you
answer by typing the numbers you want separated by commas, for example `5, 6, 4`.
Press `Enter` on its own to skip a question. After the last one it prints your matches.

> The terminal version uses numbered lists because it has to work on any machine
> without a display. The desktop app in Part 4 is the one where you type answers in
> your own words and watch it pick out the tags as you go.

### Other things you can do in the terminal

| Command | What it does |
|---|---|
| `python3 -m futureforge.cli --list-fields` | Lists every career field in the catalogue |
| `python3 -m futureforge.cli --profile examples/sample_student.json --markdown` | Prints the report as Markdown, for pasting into a document |
| `python3 -m futureforge.cli --profile examples/sample_student.json --json` | Prints the report as JSON, for feeding into other software |
| `python3 -m futureforge.cli --top 10` | Returns ten careers instead of the default five |

---

## Part 4: Run the desktop app

The desktop version shows the same results in a window, with colour coded steps
and the matched tags appearing as you type.

```bash
python3 main.py
```

**What you should see:** a window titled FutureForge opens, with the heading "Let's
find careers that fit you." Enter a name, choose a grade, and click **Start**.

If a window opens, you are done. Skip to Part 5.

### If nothing opens, or you see an error about tkinter

The desktop app uses a toolkit called Tk to draw its window. Python normally
includes it, but on macOS there are two common problems.

**Problem 1: "No module named _tkinter".** Your Python was built without Tk. This
happens with Python installed through Homebrew. Fix it by installing the version
from [python.org](https://www.python.org/downloads/), which includes Tk, or by
running:

```bash
brew install python-tk@3.13
```

**Problem 2: a window opens but is blank or draws nothing.** Your Python is linked
against a very old version of Tk. The `/usr/bin/python3` that ships with macOS uses
Tk 8.5.9, released in 2010, which does not draw correctly on modern macOS.

To check which version you have:

```bash
python3 -c "import tkinter; print(tkinter.Tk().tk.call('info','patchlevel'))"
```

**What you should see:** a version number such as `8.6.18`. Anything below 8.6 will
not draw properly, and you should install the python.org build of Python 3.13.

**Either way, the terminal version in Part 3 keeps working.** None of this affects
it, because it does not draw a window at all.

---

## Part 5: Optional extras

Everything so far runs with no installation and no internet connection. These two
additions are optional.

### AI written guidance

By default the advice attached to each career is generated from templates on your
own machine. If you have an OpenAI API key, the app can instead have a language
model write guidance aimed at the specific student.

```bash
pip3 install openai
export OPENAI_API_KEY=sk-your-key-here
python3 main.py
```

**What you should see:** the note at the bottom of the app window changes from
"Offline mode" to show that AI guidance is active.

On Windows PowerShell, set the key like this instead:

```powershell
$env:OPENAI_API_KEY = "sk-your-key-here"
```

This costs money, charged by OpenAI per request. Without a key, everything still
works. Nothing is sent over the internet and no feature is disabled, the wording of
the guidance simply comes from templates rather than a model. Results are also saved
after the first time, so asking for the same career twice does not cost twice.

### Running the tests

The project includes 34 automated tests that check the catalogue, the scoring rules
and the report formats.

```bash
pip3 install pytest
python3 -m pytest tests/ -q
```

**What you should see:** a row of dots followed by `34 passed`. No internet
connection is needed.

---

## Part 6: The cohort simulation

This runs a hundred imaginary students through the engine at once and reports which
careers came out. It is a way of checking that the matching spreads across the
catalogue instead of funnelling everyone into the same few jobs.

```bash
python3 scripts/batch_demo.py --profiles 100 --top 5
```

**What you should see:** a progress count, then a summary reporting 500
recommendations produced, how many distinct careers were surfaced, and a bar chart
of which fields came up most often.

The run is reproducible. The same command gives the same answer every time, and
`--seed 42` changes the students while keeping that property.

---

## Common problems

**"No such file or directory" when running a command.** You are not inside the
project folder. Run `cd FutureForge` first, or repeat the `cd` step in Part 2.

**"No module named futureforge".** Same cause. The command must be run from the
folder containing `main.py`. Type `ls` (or `dir` on Windows) and check that you can
see `main.py` in the list.

**"command not found: python3".** Python is not installed, or on Windows it is
called `python`. See Part 1.

**"command not found: pip3".** Try `python3 -m pip` instead, for example
`python3 -m pip install pytest`.

**The app window opens behind other windows.** Look for the FutureForge icon in
your dock or taskbar and click it.

---

## Where things live

```
main.py                  starts the desktop app
futureforge/
  wizard.py              the desktop app itself
  cli.py                 the terminal version
  matching.py            the scoring rules
  textmatch.py           turns typed answers into tags
  dataset.py             loads and checks the catalogue
  generator.py           writes the guidance, with or without AI
  report.py              formats results as text, Markdown or JSON
data/careers.json        the catalogue of 508 careers
examples/                ready made student profiles
tests/                   the automated tests
```
