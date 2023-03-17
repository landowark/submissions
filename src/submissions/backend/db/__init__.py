'''
All database related operations.
'''
from .functions import *


# from . import models
# from .models.kits import reagenttypes_kittypes
# from .models.submissions import reagents_submissions
# import pandas as pd
# import sqlalchemy.exc
# import sqlite3
# import logging
# from datetime import date, datetime, timedelta
# from sqlalchemy import and_
# import uuid
# # import base64
# from sqlalchemy import JSON, event
# from sqlalchemy.engine import Engine
# import json
# # from dateutil.relativedelta import relativedelta
# from getpass import getuser
# import numpy as np
# from tools import check_not_nan, check_is_power_user
# import yaml
# from pathlib import Path

# logger = logging.getLogger(f"submissions.{__name__}")

# # The below _should_ allow automatic creation of foreign keys in the database
# @event.listens_for(Engine, "connect")
# def set_sqlite_pragma(dbapi_connection, connection_record):
#     cursor = dbapi_connection.cursor()
#     cursor.execute("PRAGMA foreign_keys=ON")
#     cursor.close()

# def store_submission(ctx:dict, base_submission:models.BasicSubmission) -> None|dict:
#     """
#     Upserts submissions into database

#     Args:
#         ctx (dict): settings passed down from gui
#         base_submission (models.BasicSubmission): submission to be add to db

#     Returns:
#         None|dict : object that indicates issue raised for reporting in gui
#     """    
#     logger.debug(f"Hello from store_submission")
#     # Add all samples to sample table
#     for sample in base_submission.samples:
#         sample.rsl_plate = base_submission
#         logger.debug(f"Attempting to add sample: {sample.to_string()}")
#         try:
#             ctx['database_session'].add(sample)
#         except (sqlite3.IntegrityError, sqlalchemy.exc.IntegrityError) as e:
#             logger.debug(f"Hit an integrity error : {e}")
#             continue
#     # Add submission to submission table
#     ctx['database_session'].add(base_submission)
#     logger.debug(f"Attempting to add submission: {base_submission.rsl_plate_num}")
#     try:
#         ctx['database_session'].commit()
#     except (sqlite3.IntegrityError, sqlalchemy.exc.IntegrityError) as e:
#         logger.debug(f"Hit an integrity error : {e}")
#         ctx['database_session'].rollback()
#         return {"message":"This plate number already exists, so we can't add it."}
#     except (sqlite3.OperationalError, sqlalchemy.exc.IntegrityError) as e:
#         logger.debug(f"Hit an operational error: {e}")
#         ctx['database_session'].rollback()
#         return {"message":"The database is locked for editing."}
#     return None


# def store_reagent(ctx:dict, reagent:models.Reagent) -> None|dict:
#     """
#     Inserts a reagent into the database.

#     Args:
#         ctx (dict): settings passed down from gui
#         reagent (models.Reagent): Reagent object to be added to db

#     Returns:
#         None|dict: object indicating issue to be reported in the gui
#     """    
#     logger.debug(f"Reagent dictionary: {reagent.__dict__}")
#     ctx['database_session'].add(reagent)
#     try:
#         ctx['database_session'].commit()
#     except (sqlite3.OperationalError, sqlalchemy.exc.OperationalError):
#         return {"message":"The database is locked for editing."}
#     return None


# def construct_submission_info(ctx:dict, info_dict:dict) -> models.BasicSubmission:
#     """
#     Construct submission object from dictionary

#     Args:
#         ctx (dict): settings passed down from gui
#         info_dict (dict): dictionary to be transformed

#     Returns:
#         models.BasicSubmission: Constructed submission object
#     """
#     # convert submission type into model name
#     query = info_dict['submission_type'].replace(" ", "")
#     # Ensure an rsl plate number exists for the plate
#     if info_dict["rsl_plate_num"] == 'nan' or info_dict["rsl_plate_num"] == None or not check_not_nan(info_dict["rsl_plate_num"]):
#         instance = None
#         msg = "A proper RSL plate number is required."
#         return instance, {'code': 2, 'message': "A proper RSL plate number is required."}
#     # check database for existing object
#     instance = ctx['database_session'].query(models.BasicSubmission).filter(models.BasicSubmission.rsl_plate_num==info_dict['rsl_plate_num']).first()
#     # get model based on submission type converted above
#     logger.debug(f"Looking at models for submission type: {query}")
#     model = getattr(models, query)
#     logger.debug(f"We've got the model: {type(model)}")
#     info_dict['submission_type'] = info_dict['submission_type'].replace(" ", "_").lower()
#     # if query return nothing, ie doesn't already exist in db
#     if instance == None:
#         instance = model()
#         logger.debug(f"Submission doesn't exist yet, creating new instance: {instance}")
#         msg = None
#         code = 0
#     else:
#         code = 1
#         msg = "This submission already exists.\nWould you like to overwrite?"
#     for item in info_dict:
#         logger.debug(f"Setting {item} to {info_dict[item]}")
#         # set fields based on keys in dictionary
#         match item:
#             case "extraction_kit":
#                 q_str = info_dict[item]
#                 logger.debug(f"Looking up kit {q_str}")
#                 try:
#                     field_value = lookup_kittype_by_name(ctx=ctx, name=q_str)
#                 except (sqlite3.IntegrityError, sqlalchemy.exc.IntegrityError) as e:
#                     logger.error(f"Hit an integrity error: {e}")
#                 logger.debug(f"Got {field_value} for kit {q_str}")
#             case "submitting_lab":
#                 q_str = info_dict[item].replace(" ", "_").lower()
#                 logger.debug(f"Looking up organization: {q_str}")
#                 field_value = lookup_org_by_name(ctx=ctx, name=q_str)
#                 logger.debug(f"Got {field_value} for organization {q_str}")
#             case "submitter_plate_num":
#                 # Because of unique constraint, there will be problems with 
#                 # multiple submissions named 'None', so...
#                 logger.debug(f"Submitter plate id: {info_dict[item]}")
#                 if info_dict[item] == None or info_dict[item] == "None":
#                     logger.debug(f"Got None as a submitter plate number, inserting random string to preserve database unique constraint.")
#                     info_dict[item] = uuid.uuid4().hex.upper()
#                 field_value = info_dict[item]
#             case _:
#                 field_value = info_dict[item]
#         # insert into field
#         try:
#             setattr(instance, item, field_value)
#         except AttributeError:
#             logger.debug(f"Could not set attribute: {item} to {info_dict[item]}")
#             continue
#     # calculate cost of the run: immutable cost + mutable times number of columns
#     # This is now attached to submission upon creation to preserve at-run costs incase of cost increase in the future.
#     try:
#         instance.run_cost = instance.extraction_kit.immutable_cost + (instance.extraction_kit.mutable_cost * ((instance.sample_count / 8)/12))
#     except (TypeError, AttributeError):
#         logger.debug(f"Looks like that kit doesn't have cost breakdown yet, using full plate cost.")
#         instance.run_cost = instance.extraction_kit.cost_per_run
#     # We need to make sure there's a proper rsl plate number
#     try:
#         logger.debug(f"Constructed instance: {instance.to_string()}")
#     except AttributeError as e:
#         logger.debug(f"Something went wrong constructing instance {info_dict['rsl_plate_num']}: {e}")
#     logger.debug(f"Constructed submissions message: {msg}")
#     return instance, {'code':code, 'message':msg}
    

# def construct_reagent(ctx:dict, info_dict:dict) -> models.Reagent:
#     """
#     Construct reagent object from dictionary

#     Args:
#         ctx (dict): settings passed down from gui
#         info_dict (dict): dictionary to be converted

#     Returns:
#         models.Reagent: Constructed reagent object
#     """    
#     reagent = models.Reagent()
#     for item in info_dict:
#         logger.debug(f"Reagent info item: {item}")
#         # set fields based on keys in dictionary
#         match item:
#             case "lot":
#                 reagent.lot = info_dict[item].upper()
#             case "expiry":
#                 reagent.expiry = info_dict[item]
#             case "type":
#                 reagent.type = lookup_reagenttype_by_name(ctx=ctx, rt_name=info_dict[item].replace(" ", "_").lower())
#     # add end-of-life extension from reagent type to expiry date
#     # NOTE: this will now be done only in the reporting phase to account for potential changes in end-of-life extensions
#     # try:
#     #     reagent.expiry = reagent.expiry + reagent.type.eol_ext
#     # except TypeError as e:
#     #     logger.debug(f"We got a type error: {e}.")
#     # except AttributeError:
#     #     pass
#     return reagent


# def lookup_reagent(ctx:dict, reagent_lot:str) -> models.Reagent:
#     """
#     Query db for reagent based on lot number

#     Args:
#         ctx (dict): settings passed down from gui
#         reagent_lot (str): lot number to query

#     Returns:
#         models.Reagent: looked up reagent
#     """    
#     lookedup = ctx['database_session'].query(models.Reagent).filter(models.Reagent.lot==reagent_lot).first()
#     return lookedup


# def get_all_reagenttype_names(ctx:dict) -> list[str]:
#     """
#     Lookup all reagent types and get names

#     Args:
#         ctx (dict): settings passed from gui

#     Returns:
#         list[str]: reagent type names
#     """    
#     lookedup = [item.__str__() for item in ctx['database_session'].query(models.ReagentType).all()]
#     return lookedup


# def lookup_reagenttype_by_name(ctx:dict, rt_name:str) -> models.ReagentType:
#     """
#     Lookup a single reagent type by name

#     Args:
#         ctx (dict): settings passed from gui
#         rt_name (str): reagent type name to look up

#     Returns:
#         models.ReagentType: looked up reagent type
#     """    
#     logger.debug(f"Looking up ReagentType by name: {rt_name}")
#     lookedup = ctx['database_session'].query(models.ReagentType).filter(models.ReagentType.name==rt_name).first()
#     logger.debug(f"Found ReagentType: {lookedup}")
#     return lookedup


# def lookup_kittype_by_use(ctx:dict, used_by:str) -> list[models.KitType]:
#     """
#     Lookup kits by a sample type its used for

#     Args:
#         ctx (dict): settings passed from gui
#         used_by (str): sample type (should be string in D3 of excel sheet)

#     Returns:
#         list[models.KitType]: list of kittypes that have that sample type in their uses
#     """    
#     return ctx['database_session'].query(models.KitType).filter(models.KitType.used_for.contains(used_by)).all()


# def lookup_kittype_by_name(ctx:dict, name:str) -> models.KitType:
#     """
#     Lookup a kit type by name

#     Args:
#         ctx (dict): settings passed from bui
#         name (str): name of kit to query

#     Returns:
#         models.KitType: retrieved kittype
#     """    
#     logger.debug(f"Querying kittype: {name}")
#     return ctx['database_session'].query(models.KitType).filter(models.KitType.name==name).first()
    

# def lookup_regent_by_type_name(ctx:dict, type_name:str) -> list[models.Reagent]:
#     """
#     Lookup reagents by their type name

#     Args:
#         ctx (dict): settings passed from gui
#         type_name (str): reagent type name

#     Returns:
#         list[models.Reagent]: list of retrieved reagents
#     """    
#     return ctx['database_session'].query(models.Reagent).join(models.Reagent.type, aliased=True).filter(models.ReagentType.name==type_name).all()


# def lookup_regent_by_type_name_and_kit_name(ctx:dict, type_name:str, kit_name:str) -> list[models.Reagent]:
#     """
#     Lookup reagents by their type name and kits they belong to (Broken... maybe cursed, I'm not sure.)

#     Args:
#         ctx (dict): settings pass by gui
#         type_name (str): reagent type name
#         kit_name (str): kit name

#     Returns:
#         list[models.Reagent]: list of retrieved reagents
#     """    
#     # What I want to do is get the reagent type by name 
#     # Hang on, this is going to be a long one.
#     # by_type = ctx['database_session'].query(models.Reagent).join(models.Reagent.type, aliased=True).filter(models.ReagentType.name.endswith(type_name)).all()
#     rt_types = ctx['database_session'].query(models.ReagentType).filter(models.ReagentType.name.endswith(type_name))
#     # add filter for kit name... 
#     try:
#         check = not np.isnan(kit_name)
#     except TypeError:
#         check = True
#     if check:
#         kit_type = lookup_kittype_by_name(ctx=ctx, name=kit_name)
#         logger.debug(f"reagenttypes: {[item.name for item in rt_types.all()]}, kit: {kit_type.name}")
#         # add in lookup for related kit_id
#         rt_types = rt_types.join(reagenttypes_kittypes).filter(reagenttypes_kittypes.c.kits_id==kit_type.id).first()
#     else:
#         rt_types = rt_types.first()
#     output = rt_types.instances
#     return output


# def lookup_all_submissions_by_type(ctx:dict, sub_type:str|None=None) -> list[models.BasicSubmission]:
#     """
#     Get all submissions, filtering by type if given

#     Args:
#         ctx (dict): settings pass from gui
#         type (str | None, optional): submission type (should be string in D3 of excel sheet). Defaults to None.

#     Returns:
#         list[models.BasicSubmission]: list of retrieved submissions
#     """
#     if sub_type == None:
#         subs = ctx['database_session'].query(models.BasicSubmission).all()
#     else:
#         subs = ctx['database_session'].query(models.BasicSubmission).filter(models.BasicSubmission.submission_type==sub_type.lower().replace(" ", "_")).all()
#     return subs

# def lookup_all_orgs(ctx:dict) -> list[models.Organization]:
#     """
#     Lookup all organizations (labs)

#     Args:
#         ctx (dict): settings passed from gui

#     Returns:
#         list[models.Organization]: list of retrieved organizations
#     """    
#     return ctx['database_session'].query(models.Organization).all()

# def lookup_org_by_name(ctx:dict, name:str|None) -> models.Organization:
#     """
#     Lookup organization (lab) by (startswith) name.

#     Args:
#         ctx (dict): settings passed from gui
#         name (str | None): name of organization

#     Returns:
#         models.Organization: retrieved organization
#     """    
#     logger.debug(f"Querying organization: {name}")
#     return ctx['database_session'].query(models.Organization).filter(models.Organization.name.startswith(name)).first()

# def submissions_to_df(ctx:dict, sub_type:str|None=None) -> pd.DataFrame:
#     """
#     Convert submissions looked up by type to dataframe

#     Args:
#         ctx (dict): settings passed by gui
#         type (str | None, optional): submission type (should be string in D3 of excel sheet) Defaults to None.

#     Returns:
#         pd.DataFrame: dataframe constructed from retrieved submissions
#     """    
#     logger.debug(f"Type: {sub_type}")
#     # use lookup function to create list of dicts
#     subs = [item.to_dict() for item in lookup_all_submissions_by_type(ctx=ctx, sub_type=sub_type)]
#     # make df from dicts (records) in list
#     df = pd.DataFrame.from_records(subs)
#     # Exclude sub information
#     try:
#         df = df.drop("controls", axis=1)
#     except:
#         logger.warning(f"Couldn't drop 'controls' column from submissionsheet df.")
#     try:
#         df = df.drop("ext_info", axis=1)
#     except:
#         logger.warning(f"Couldn't drop 'controls' column from submissionsheet df.")
#     return df
     
    
# def lookup_submission_by_id(ctx:dict, id:int) -> models.BasicSubmission:
#     """
#     Lookup submission by id number

#     Args:
#         ctx (dict): settings passed from gui
#         id (int): submission id number

#     Returns:
#         models.BasicSubmission: retrieved submission
#     """    
#     return ctx['database_session'].query(models.BasicSubmission).filter(models.BasicSubmission.id==id).first()


# def lookup_submissions_by_date_range(ctx:dict, start_date:datetime.date, end_date:datetime.date) -> list[models.BasicSubmission]:
#     """
#     Lookup submissions greater than start_date and less than end_date

#     Args:
#         ctx (dict): settings passed from gui
#         start_date (datetime.date): date to start looking
#         end_date (datetime.date): date to end looking

#     Returns:
#         list[models.BasicSubmission]: list of retrieved submissions
#     """    
#     # return ctx['database_session'].query(models.BasicSubmission).filter(and_(models.BasicSubmission.submitted_date > start_date, models.BasicSubmission.submitted_date < end_date)).all()
#     start_date = start_date.strftime("%Y-%m-%d")
#     end_date = end_date.strftime("%Y-%m-%d")
#     return ctx['database_session'].query(models.BasicSubmission).filter(models.BasicSubmission.submitted_date.between(start_date, end_date)).all()


# def get_all_Control_Types_names(ctx:dict) -> list[str]:
#     """
#     Grabs all control type names from db.

#     Args:
#         settings (dict): settings passed down from gui.

#     Returns:
#         list: list of controltype names
#     """    
#     conTypes = ctx['database_session'].query(models.ControlType).all()
#     conTypes = [conType.name for conType in conTypes]
#     logger.debug(f"Control Types: {conTypes}")
#     return conTypes


# def create_kit_from_yaml(ctx:dict, exp:dict) -> dict:
#     """
#     Create and store a new kit in the database based on a .yml file
#     TODO: split into create and store functions

#     Args:
#         ctx (dict): Context dictionary passed down from frontend
#         exp (dict): Experiment dictionary created from yaml file

#     Returns:
#         dict: a dictionary containing results of db addition
#     """    
#     # Don't want just anyone adding kits
#     if not check_is_power_user(ctx=ctx):
#         logger.debug(f"{getuser()} does not have permission to add kits.")
#         return {'code':1, 'message':"This user does not have permission to add kits.", "status":"warning"}
#     # iterate through keys in dict
#     for type in exp:
#         if type == "password":
#             continue
#         # A submission type may use multiple kits.
#         for kt in exp[type]['kits']:
#             kit = models.KitType(name=kt, used_for=[type.replace("_", " ").title()], constant_cost=exp[type]["kits"][kt]["constant_cost"], mutable_cost=exp[type]["kits"][kt]["mutable_cost"])
#             # A kit contains multiple reagent types.
#             for r in exp[type]['kits'][kt]['reagenttypes']:
#                 # check if reagent type already exists.
#                 look_up = ctx['database_session'].query(models.ReagentType).filter(models.ReagentType.name==r).first()
#                 if look_up == None:
#                     rt = models.ReagentType(name=r.replace(" ", "_").lower(), eol_ext=timedelta(30*exp[type]['kits'][kt]['reagenttypes'][r]['eol_ext']), kits=[kit])
#                 else:
#                     rt = look_up
#                     rt.kits.append(kit)
#                     # add this because I think it's necessary to get proper back population
#                     kit.reagent_types_id.append(rt.id)
#                 ctx['database_session'].add(rt)
#                 logger.debug(f"Kit construction reagent type: {rt.__dict__}")
#             logger.debug(f"Kit construction kit: {kit.__dict__}")
#         ctx['database_session'].add(kit)
#     ctx['database_session'].commit()
#     return {'code':0, 'message':'Kit has been added', 'status': 'information'}


# def create_org_from_yaml(ctx:dict, org:dict) -> dict:
#     """
#     Create and store a new organization based on a .yml file

#     Args:
#         ctx (dict): Context dictionary passed down from frontend
#         org (dict): Dictionary containing organization info.

#     Returns:
#         dict: dictionary containing results of db addition
#     """    
#     # Don't want just anyone adding in clients
#     if not check_is_power_user(ctx=ctx):
#         logger.debug(f"{getuser()} does not have permission to add kits.")
#         return {'code':1, 'message':"This user does not have permission to add organizations."}
#     # the yml can contain multiple clients
#     for client in org:
#         cli_org = models.Organization(name=client.replace(" ", "_").lower(), cost_centre=org[client]['cost centre'])
#         # a client can contain multiple contacts
#         for contact in org[client]['contacts']:
#             cont_name = list(contact.keys())[0]
#             # check if contact already exists
#             look_up = ctx['database_session'].query(models.Contact).filter(models.Contact.name==cont_name).first()
#             if look_up == None:
#                 cli_cont = models.Contact(name=cont_name, phone=contact[cont_name]['phone'], email=contact[cont_name]['email'], organization=[cli_org])
#             else:
#                 cli_cont = look_up
#                 cli_cont.organization.append(cli_org)
#             ctx['database_session'].add(cli_cont)
#             logger.debug(f"Client creation contact: {cli_cont.__dict__}")
#         logger.debug(f"Client creation client: {cli_org.__dict__}")
#         ctx['database_session'].add(cli_org)
#     ctx["database_session"].commit()
#     return {"code":0, "message":"Organization has been added."}


# def lookup_all_sample_types(ctx:dict) -> list[str]:
#     """
#     Lookup all sample types and get names

#     Args:
#         ctx (dict): settings pass from gui

#     Returns:
#         list[str]: list of sample type names
#     """    
#     uses = [item.used_for for item in ctx['database_session'].query(models.KitType).all()]
#     # flattened list of lists
#     uses = list(set([item for sublist in uses for item in sublist]))
#     return uses


# def get_all_available_modes(ctx:dict) -> list[str]:
#     """
#     Get types of analysis for controls

#     Args:
#         ctx (dict): settings passed from gui

#     Returns:
#         list[str]: list of analysis types
#     """    
#     # Only one control is necessary since they all share the same control types.
#     rel = ctx['database_session'].query(models.Control).first()
#     try:
#         cols = [item.name for item in list(rel.__table__.columns) if isinstance(item.type, JSON)]
#     except AttributeError as e:
#         logger.debug(f"Failed to get available modes from db: {e}")
#         cols = []
#     return cols


# def get_all_controls_by_type(ctx:dict, con_type:str, start_date:date|None=None, end_date:date|None=None) -> list[models.Control]:
#     """
#     Returns a list of control objects that are instances of the input controltype.
#     Between dates if supplied.

#     Args:
#         ctx (dict): Settings passed down from gui
#         con_type (str): Name of control type.
#         start_date (date | None, optional): Start date of query. Defaults to None.
#         end_date (date | None, optional): End date of query. Defaults to None.

#     Returns:
#         list[models.Control]: list of control samples.
#     """    
#     logger.debug(f"Using dates: {start_date} to {end_date}")
#     if start_date != None and end_date != None:
#         start_date = start_date.strftime("%Y-%m-%d")
#         end_date = end_date.strftime("%Y-%m-%d")
#         output = ctx['database_session'].query(models.Control).join(models.ControlType).filter_by(name=con_type).filter(models.Control.submitted_date.between(start_date, end_date)).all()
#     else:
#         output = ctx['database_session'].query(models.Control).join(models.ControlType).filter_by(name=con_type).all()
#     logger.debug(f"Returned controls between dates: {output}")
#     return output


# def get_control_subtypes(ctx:dict, type:str, mode:str) -> list[str]:
#     """
#     Get subtypes for a control analysis mode

#     Args:
#         ctx (dict): settings passed from gui
#         type (str): control type name
#         mode (str): analysis mode name

#     Returns:
#         list[str]: list of subtype names
#     """    
#     # Only the first control of type is necessary since they all share subtypes
#     try:
#         outs = get_all_controls_by_type(ctx=ctx, con_type=type)[0]
#     except TypeError:
#         return []
#     # Get analysis mode data as dict
#     jsoner = json.loads(getattr(outs, mode))
#     logger.debug(f"JSON out: {jsoner}")
#     try:
#         genera = list(jsoner.keys())[0]
#     except IndexError:
#         return []
#     subtypes = [item for item in jsoner[genera] if "_hashes" not in item and "_ratio" not in item]
#     return subtypes


# def get_all_controls(ctx:dict) -> list[models.Control]:
#     """
#     Retrieve a list of all controls from the database

#     Args:
#         ctx (dict): settings passed down from the gui.

#     Returns:
#         list[models.Control]: list of all control objects
#     """    
#     return ctx['database_session'].query(models.Control).all()


# def lookup_submission_by_rsl_num(ctx:dict, rsl_num:str) -> models.BasicSubmission:
#     """
#     Retrieve a submission from the database based on rsl plate number

#     Args:
#         ctx (dict): settings passed down from gui
#         rsl_num (str): rsl plate number

#     Returns:
#         models.BasicSubmission: Submissions object retrieved from database
#     """
#     return ctx['database_session'].query(models.BasicSubmission).filter(models.BasicSubmission.rsl_plate_num.startswith(rsl_num)).first()


# def lookup_submissions_using_reagent(ctx:dict, reagent:models.Reagent) -> list[models.BasicSubmission]:
#     return ctx['database_session'].query(models.BasicSubmission).join(reagents_submissions).filter(reagents_submissions.c.reagent_id==reagent.id).all()


# def delete_submission_by_id(ctx:dict, id:int) -> None:
#     """
#     Deletes a submission and its associated samples from the database.

#     Args:
#         ctx (dict): settings passed down from gui
#         id (int): id of submission to be deleted.
#     """    
#     # In order to properly do this Im' going to have to delete all of the secondary table stuff as well.
#     # Retrieve submission
#     sub = ctx['database_session'].query(models.BasicSubmission).filter(models.BasicSubmission.id==id).first()
#     # Convert to dict for storing backup as a yml
#     backup = sub.to_dict()
#     try:
#         with open(Path(ctx['backup_path']).joinpath(f"{sub.rsl_plate_num}-backup({date.today().strftime('%Y%m%d')}).yml"), "w") as f:
#             yaml.dump(backup, f)
#     except KeyError:
#         pass
#     sub.reagents = []
#     for sample in sub.samples:
#         ctx['database_session'].delete(sample)
#     ctx["database_session"].delete(sub)
#     ctx["database_session"].commit()