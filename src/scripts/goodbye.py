"""
Test script for teardown_scripts
"""


def goodbye(ctx):
    """
    Args:
        ctx (Settings): All scripts must take ctx as an argument to maintain interoperability.

    Returns:
        None: Scripts are currently unable to return results to the program.
    """
    print("\n\nGoodbye. Thank you for using Robotics Submission Tracker.\n\n")


"""
For scripts to be procedure, they must be added to the _configitem.startup_scripts or _configitem.teardown_scripts
rows as a key: value (name: null) entry in the JSON.
ex: {"goodbye": null, "backup_database": null}
The program will overwrite null with the actual function upon startup.
"""
