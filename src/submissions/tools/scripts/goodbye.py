"""
Test script for teardown_scripts
"""

from .. import register_script

@register_script
def goodbye(ctx):
    print("\n\nGoodbye. Thank you for using Robotics Submission Tracker.\n\n")
