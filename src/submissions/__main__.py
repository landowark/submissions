import sys
from pathlib import Path
import os
# must be set to enable qtwebengine in network path
if getattr(sys, 'frozen', False):
    os.environ['QTWEBENGINE_DISABLE_SANDBOX'] = "1"
else :
    pass
from configure import get_config, create_database_session, setup_logger
# setup custom logger
logger = setup_logger(verbosity=3)
# import config
ctx = get_config(None)
from PyQt6.QtWidgets import QApplication
from frontend import App
import __init__ as package

# create database session for use with gui session
ctx["database_session"] = create_database_session(Path(ctx['database']))
# set package information fro __init__
ctx['package'] = package

if __name__ == '__main__':
    # 
    app = QApplication(['', '--no-sandbox'])
    ex = App(ctx=ctx)
    sys.exit(app.exec())



# from pathlib import Path

# from tkinter import *
# from tkinter import filedialog as fd
# from tkinter import ttk
# from tkinterhtml import HtmlFrame

# from xl_parser import SheetParser

# class Window(Frame):
#     def __init__(self, master=None):
#         Frame.__init__(self, master)
#         self.master = master
#         # Frame.pack_propagate(False) 
#         menu = Menu(self.master)
#         self.master.config(menu=menu)

#         fileMenu = Menu(menu)
#         fileMenu.add_command(label="Import", command=self.import_callback)
#         fileMenu.add_command(label="Exit", command=self.exitProgram)
#         menu.add_cascade(label="File", menu=fileMenu)

#         editMenu = Menu(menu)
#         editMenu.add_command(label="Undo")
#         editMenu.add_command(label="Redo")
#         menu.add_cascade(label="Edit", menu=editMenu)

#         tab_parent = ttk.Notebook(self.master)
#         self.add_sample_tab = ttk.Frame(tab_parent)
#         self.control_view_tab = HtmlFrame(tab_parent)
#         tab_parent.add(self.add_sample_tab, text="Add Sample")
#         tab_parent.add(self.control_view_tab, text="Controls View")
#         tab_parent.pack()
#         with open("L:\Robotics Laboratory Support\Quality\Robotics Support Laboratory Extraction Controls\MCS-SSTI.html", "r") as f:
#             data = f.read()
#         # frame = 
#         # frame.set_content(data)
#         # self.control_view_tab.set_content("""
#         #         <html>
#         #         <body>
#         #         <h1>Hello world!</h1>
#         #         <p>First para</p>
#         #         <ul>
#         #             <li>first list item</li>
#         #             <li>second list item</li>
#         #         </ul>
#         #         <img src="http://findicons.com/files/icons/638/magic_people/128/magic_ball.png"/>
#         #         </body>
#         #         </html>    
#         # """)

        

#     def exitProgram(self):
#         exit()

#     def import_callback(self):
#         name= fd.askopenfilename()
#         prsr = SheetParser(Path(name), **ctx)
#         for item in prsr.sub:
#             lbl=Label(self.add_sample_tab, text=item, fg='red', font=("Helvetica", 16))
#             lbl.pack()
#             txtfld=Entry(self.add_sample_tab, text="Data not set", bd=2)
#             txtfld.pack()
#             txtfld.delete(0,END)
#             txtfld.insert(0,prsr.sub[item])
        
        
# root = Tk()
# app = Window(root)
# # for item in test_data:
# #     lbl=Label(root, text=item, fg='red', font=("Helvetica", 16))
# #     lbl.pack()
# #     txtfld=Entry(root, text="", bd=2)
# #     txtfld.pack()
# #     txtfld.delete(0,END)
# #     txtfld.insert(0,test_data[item])
# root.wm_title("Tkinter window")
# root.mainloop()