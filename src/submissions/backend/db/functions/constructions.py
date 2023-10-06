'''
Used to construct models from input dictionaries.
'''
from getpass import getuser
from tools import Settings, RSLNamer, check_regex_match
from .. import models
from .lookups import *
import logging
from datetime import date, timedelta
from dateutil.parser import parse
from typing import Tuple
from sqlalchemy.exc import IntegrityError, SAWarning
from . import store_object

logger = logging.getLogger(f"submissions.{__name__}")

def construct_reagent(ctx:Settings, info_dict:dict) -> models.Reagent:
    """
    Construct reagent object from dictionary

    Args:
        ctx (Settings): settings object passed down from gui
        info_dict (dict): dictionary to be converted

    Returns:
        models.Reagent: Constructed reagent object
    """    
    reagent = models.Reagent()
    for item in info_dict:
        logger.debug(f"Reagent info item for {item}: {info_dict[item]}")
        # set fields based on keys in dictionary
        match item:
            case "lot":
                reagent.lot = info_dict[item].upper()
            case "expiry":
                if isinstance(info_dict[item], date):
                    reagent.expiry = info_dict[item]
                else:
                    reagent.expiry = parse(info_dict[item]).date()
            case "type":
                reagent_type = lookup_reagent_types(ctx=ctx, name=info_dict[item])
                if reagent_type != None:
                    reagent.type.append(reagent_type)
            case "name":
                if item == None:
                    reagent.name = reagent.type.name
                else:
                    reagent.name = info_dict[item]
    # add end-of-life extension from reagent type to expiry date
    # NOTE: this will now be done only in the reporting phase to account for potential changes in end-of-life extensions
    return reagent

def construct_submission_info(ctx:Settings, info_dict:dict) -> Tuple[models.BasicSubmission, dict]:
    """
    Construct submission object from dictionary pulled from gui form

    Args:
        ctx (Settings): settings object passed down from gui
        info_dict (dict): dictionary to be transformed

    Returns:
        models.BasicSubmission: Constructed submission object
    """
    # convert submission type into model name
    query = info_dict['submission_type'].replace(" ", "")
    # Ensure an rsl plate number exists for the plate
    if not check_regex_match("^RSL", info_dict["rsl_plate_num"]):
        instance = None
        msg = "A proper RSL plate number is required."
        return instance, {'code': 2, 'message': "A proper RSL plate number is required."}
    else:
        # enforce conventions on the rsl plate number from the form
        info_dict['rsl_plate_num'] = RSLNamer(ctx=ctx, instr=info_dict["rsl_plate_num"]).parsed_name
    # check database for existing object
    instance = lookup_submissions(ctx=ctx, rsl_number=info_dict['rsl_plate_num'])
    # get model based on submission type converted above
    logger.debug(f"Looking at models for submission type: {query}")
    model = getattr(models, query)
    logger.debug(f"We've got the model: {type(model)}")
    # if query return nothing, ie doesn't already exist in db
    if instance == None:
        instance = model()
        logger.debug(f"Submission doesn't exist yet, creating new instance: {instance}")
        msg = None
        code = 0
    else:
        code = 1
        msg = "This submission already exists.\nWould you like to overwrite?"
    for item in info_dict:
        value = info_dict[item]
        logger.debug(f"Setting {item} to {value}")
        # set fields based on keys in dictionary
        match item:
            case "extraction_kit":
                logger.debug(f"Looking up kit {value}")
                field_value = lookup_kit_types(ctx=ctx, name=value)
                logger.debug(f"Got {field_value} for kit {value}")
            case "submitting_lab":
                logger.debug(f"Looking up organization: {value}")
                field_value = lookup_organizations(ctx=ctx, name=value)
                logger.debug(f"Got {field_value} for organization {value}")
            case "submitter_plate_num":
                logger.debug(f"Submitter plate id: {value}")
                field_value = value
            case "samples":
                instance = construct_samples(ctx=ctx, instance=instance, samples=value)
                continue
            case "submission_type":
                field_value = lookup_submission_type(ctx=ctx, name=value)            
            case _:
                field_value = value
        # insert into field
        try:
            setattr(instance, item, field_value)
        except AttributeError:
            logger.debug(f"Could not set attribute: {item} to {info_dict[item]}")
            continue
        except KeyError:
            continue
    # calculate cost of the run: immutable cost + mutable times number of columns
    # This is now attached to submission upon creation to preserve at-run costs incase of cost increase in the future.
    try:
        logger.debug(f"Calculating costs for procedure...")
        instance.calculate_base_cost()
    except (TypeError, AttributeError) as e:
        logger.debug(f"Looks like that kit doesn't have cost breakdown yet due to: {e}, using full plate cost.")
        instance.run_cost = instance.extraction_kit.cost_per_run
    logger.debug(f"Calculated base run cost of: {instance.run_cost}")
    # Apply any discounts that are applicable for client and kit.
    try:
        logger.debug("Checking and applying discounts...")
        discounts = [item.amount for item in lookup_discounts(ctx=ctx, kit_type=instance.extraction_kit, organization=instance.submitting_lab)]
        logger.debug(f"We got discounts: {discounts}")
        if len(discounts) > 0:
            discounts = sum(discounts)
            instance.run_cost = instance.run_cost - discounts
    except Exception as e:
        logger.error(f"An unknown exception occurred when calculating discounts: {e}")
    # We need to make sure there's a proper rsl plate number
    logger.debug(f"We've got a total cost of {instance.run_cost}")
    try:
        logger.debug(f"Constructed instance: {instance.to_string()}")
    except AttributeError as e:
        logger.debug(f"Something went wrong constructing instance {info_dict['rsl_plate_num']}: {e}")
    logger.debug(f"Constructed submissions message: {msg}")
    return instance, {'code':code, 'message':msg}

def construct_samples(ctx:Settings, instance:models.BasicSubmission, samples:List[dict]) -> models.BasicSubmission:
    """
    constructs sample objects and adds to submission

    Args:
        ctx (Settings): settings passed down from gui
        instance (models.BasicSubmission): Submission samples scraped from.
        samples (List[dict]): List of parsed samples

    Returns:
        models.BasicSubmission: Updated submission object.
    """    
    for sample in samples:
        sample_instance = lookup_samples(ctx=ctx, submitter_id=str(sample['sample'].submitter_id))
        if sample_instance == None:
            sample_instance = sample['sample']
        else:
            logger.warning(f"Sample {sample} already exists, creating association.")
        logger.debug(f"Adding {sample_instance.__dict__}")
        if sample_instance in instance.samples:
            logger.error(f"Looks like there's a duplicate sample on this plate: {sample_instance.submitter_id}!")
            continue
        try:
            with ctx.database_session.no_autoflush:
                try:
                    sample_query = sample_instance.sample_type.replace('Sample', '').strip()
                    logger.debug(f"Here is the sample instance type: {sample_instance}")
                    try:
                        assoc = getattr(models, f"{sample_query}Association")
                    except AttributeError as e:
                        logger.error(f"Couldn't get type specific association using {sample_instance.sample_type.replace('Sample', '').strip()}. Getting generic.")
                        assoc = models.SubmissionSampleAssociation
                    assoc = assoc(submission=instance, sample=sample_instance, row=sample['row'], column=sample['column'])
                    instance.submission_sample_associations.append(assoc)
                except IntegrityError:
                    logger.error(f"Hit integrity error for: {sample}")
                    continue
                except SAWarning:
                    logger.error(f"Looks like the association already exists for submission: {instance} and sample: {sample_instance}")
                    continue
        except IntegrityError as e:
            logger.critical(e)
            continue
    return instance

def construct_kit_from_yaml(ctx:Settings, kit_dict:dict) -> dict:
    """
    Create and store a new kit in the database based on a .yml file
    TODO: split into create and store functions

    Args:
        ctx (Settings): Context object passed down from frontend
        exp (dict): Experiment dictionary created from yaml file

    Returns:
        dict: a dictionary containing results of db addition
    """    
    from tools import check_is_power_user, massage_common_reagents
    # Don't want just anyone adding kits
    if not check_is_power_user(ctx=ctx):
        logger.debug(f"{getuser()} does not have permission to add kits.")
        return {'code':1, 'message':"This user does not have permission to add kits.", "status":"warning"}
    submission_type = lookup_submission_type(ctx=ctx, name=kit_dict['used_for'])
    logger.debug(f"Looked up submission type: {kit_dict['used_for']} and got {submission_type}")
    kit = models.KitType(name=kit_dict["kit_name"])
    kt_st_assoc = models.SubmissionTypeKitTypeAssociation(kit_type=kit, submission_type=submission_type)
    for k,v in kit_dict.items():
        if k not in ["reagent_types", "kit_name", "used_for"]:
            kt_st_assoc.set_attrib(k, v)
    kit.kit_submissiontype_associations.append(kt_st_assoc)
    # A kit contains multiple reagent types.
    for r in kit_dict['reagent_types']:
        # check if reagent type already exists.
        logger.debug(f"Constructing reagent type: {r}")
        rtname = massage_common_reagents(r['rtname'])
        # look_up = ctx.database_session.query(models.ReagentType).filter(models.ReagentType.name==rtname).first()
        look_up = lookup_reagent_types(name=rtname)
        if look_up == None:
            rt = models.ReagentType(name=rtname.strip(), eol_ext=timedelta(30*r['eol']))
        else:
            rt = look_up
        uses = {kit_dict['used_for']:{k:v for k,v in r.items() if k not in ['eol']}}
        assoc = models.KitTypeReagentTypeAssociation(kit_type=kit, reagent_type=rt, uses=uses)
        # ctx.database_session.add(rt)
        store_object(ctx=ctx, object=rt)
        kit.kit_reagenttype_associations.append(assoc)
        logger.debug(f"Kit construction reagent type: {rt.__dict__}")
    logger.debug(f"Kit construction kit: {kit.__dict__}")
    store_object(ctx=ctx, object=kit)
    return {'code':0, 'message':'Kit has been added', 'status': 'information'}

def construct_org_from_yaml(ctx:Settings, org:dict) -> dict:
    """
    Create and store a new organization based on a .yml file

    Args:
        ctx (Settings): Context object passed down from frontend
        org (dict): Dictionary containing organization info.

    Returns:
        dict: dictionary containing results of db addition
    """    
    from tools import check_is_power_user
    # Don't want just anyone adding in clients
    if not check_is_power_user(ctx=ctx):
        logger.debug(f"{getuser()} does not have permission to add kits.")
        return {'code':1, 'message':"This user does not have permission to add organizations."}
    # the yml can contain multiple clients
    for client in org:
        cli_org = models.Organization(name=client.replace(" ", "_").lower(), cost_centre=org[client]['cost centre'])
        # a client can contain multiple contacts
        for contact in org[client]['contacts']:
            cont_name = list(contact.keys())[0]
            # check if contact already exists
            look_up = ctx.database_session.query(models.Contact).filter(models.Contact.name==cont_name).first()
            if look_up == None:
                cli_cont = models.Contact(name=cont_name, phone=contact[cont_name]['phone'], email=contact[cont_name]['email'], organization=[cli_org])
            else:
                cli_cont = look_up
                cli_cont.organization.append(cli_org)
            ctx.database_session.add(cli_cont)
            logger.debug(f"Client creation contact: {cli_cont.__dict__}")
        logger.debug(f"Client creation client: {cli_org.__dict__}")
        ctx.database_session.add(cli_org)
    ctx.database_session.commit()
    return {"code":0, "message":"Organization has been added."}

