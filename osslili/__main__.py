"""Run osslili as a module: python -m osslili.

The console script sits wherever the installer put it, which is not always
beside the interpreter running it. A test that looked for it there found
nothing and skipped, so a whole file of assertions passed without ever
running the tool. Invoking the module leaves no doubt which code answered.
"""

from osslili.cli import main

if __name__ == "__main__":
    main()
