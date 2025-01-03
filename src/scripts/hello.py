"""
Test script for startup_scripts
"""


def hello(ctx) -> None:
    """
    Args:
        ctx (Settings): All scripts must take ctx as an argument to maintain interoperability.

    Returns:
        None: Scripts are currently unable to return results to the program.
    """
    print("\n\nHello! Welcome to Robotics Submission Tracker.\n\n")


"""
For scripts to be run, they must be added to the _configitem.startup_scripts or _configitem.teardown_scripts
rows as a key: value (name: null) entry in the JSON.
ex: {"hello": null, "import_irida": null}
The program will overwrite null with the actual function upon startup.
"""
