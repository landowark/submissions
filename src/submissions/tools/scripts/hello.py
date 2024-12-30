"""
Test script for startup_scripts
"""
from .. import register_script

@register_script
def hello(ctx):
    print("\n\nHello! Welcome to Robotics Submission Tracker.\n\n")
