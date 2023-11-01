from .. import models
from tools import Settings
# from backend.namer import RSLNamer
from typing import List
import logging
from datetime import date, datetime
from dateutil.parser import parse
from sqlalchemy.orm.query import Query
from sqlalchemy import and_, JSON
from sqlalchemy.orm import Session

logger = logging.getLogger(f"submissions.{__name__}")

def query_return(query:Query, limit:int=0):
    with query.session.no_autoflush:
        match limit:
            case 0:
                return query.all()
            case 1:
                return query.first()
            case _:
                return query.limit(limit).all()
        
def setup_lookup(ctx:Settings, locals:dict) -> Session:
    for k, v in locals.items():
        if k == "kwargs":
            continue
        if isinstance(v, dict):
            raise ValueError("Cannot use dictionary in query. Make sure you parse it first.")
    # return create_database_session(ctx=ctx)
    return ctx.database_session

################## Basic Lookups ####################################

def lookup_reagents(ctx:Settings, 
                        reagent_type:str|models.ReagentType|None=None,
                        lot_number:str|None=None,
                        limit:int=0
                        ) -> models.Reagent|List[models.Reagent]:
    """
    Lookup a list of reagents from the database.

    Args:
        ctx (Settings): Settings object passed down from gui
        reagent_type (str | models.ReagentType | None, optional): Reagent type. Defaults to None.
        lot_number (str | None, optional): Reagent lot number. Defaults to None.
        limit (int, optional): limit of results returned. Defaults to 0.

    Returns:
        models.Reagent | List[models.Reagent]: reagent or list of reagents matching filter.
    """    
    query = setup_lookup(ctx=ctx, locals=locals()).query(models.Reagent)
    match reagent_type:
        case str():
            logger.debug(f"Looking up reagents by reagent type: {reagent_type}")
            query = query.join(models.Reagent.type, aliased=True).filter(models.ReagentType.name==reagent_type)
        case models.ReagentType():
            logger.debug(f"Looking up reagents by reagent type: {reagent_type}")
            query = query.filter(models.Reagent.type.contains(reagent_type))
        case _:
            pass
    match lot_number:
        case str():
            logger.debug(f"Looking up reagent by lot number: {lot_number}")
            query = query.filter(models.Reagent.lot==lot_number)
            # In this case limit number returned.
            limit = 1
        case _:
            pass
    return query_return(query=query, limit=limit)
        
def lookup_kit_types(ctx:Settings,
                    name:str=None,
                    used_for:str|None=None,
                    id:int|None=None,
                    limit:int=0
                    ) -> models.KitType|List[models.KitType]:
    query = setup_lookup(ctx=ctx, locals=locals()).query(models.KitType)
    match used_for:
        case str():
            logger.debug(f"Looking up kit type by use: {used_for}")
            query = query.filter(models.KitType.used_for.any(name=used_for))
        case _:
            pass
    match name:
        case str():
            logger.debug(f"Looking up kit type by name: {name}")
            query = query.filter(models.KitType.name==name)
            limit = 1
        case _:
            pass
    match id:
        case int():
            logger.debug(f"Looking up kit type by id: {id}")
            query = query.filter(models.KitType.id==id)
            limit = 1
        case str():
            logger.debug(f"Looking up kit type by id: {id}")
            query = query.filter(models.KitType.id==int(id))
            limit = 1
        case _:
            pass
    return query_return(query=query, limit=limit)

def lookup_reagent_types(ctx:Settings,
                         name: str|None=None,
                         kit_type: models.KitType|str|None=None,
                         reagent: models.Reagent|str|None=None,
                         limit:int=0,
                         ) -> models.ReagentType|List[models.ReagentType]:
    """
    _summary_

    Args:
        ctx (Settings): Settings object passed down from gui.
        name (str | None, optional): Reagent type name. Defaults to None.
        limit (int, optional): limit of results to return. Defaults to 0.

    Returns:
        models.ReagentType|List[models.ReagentType]: ReagentType or list of ReagentTypes matching filter.
    """
    query = setup_lookup(ctx=ctx, locals=locals()).query(models.ReagentType)
    if (kit_type != None and reagent == None) or (reagent != None and kit_type == None):
        raise ValueError("Cannot filter without both reagent and kit type.")
    elif kit_type == None and reagent == None:
        pass
    else:
        match kit_type:
            case str():
                kit_type = lookup_kit_types(ctx=ctx, name=kit_type)
            case _:
                pass
        match reagent:
            case str():
                reagent = lookup_reagents(ctx=ctx, lot_number=reagent)
            case _:
                pass
        assert reagent.type != []
        logger.debug(f"Looking up reagent type for {type(kit_type)} {kit_type} and {type(reagent)} {reagent}")
        logger.debug(f"Kit reagent types: {kit_type.reagent_types}")
        # logger.debug(f"Reagent reagent types: {reagent._sa_instance_state}")
        result = list(set(kit_type.reagent_types).intersection(reagent.type))
        logger.debug(f"Result: {result}")
        try:
            return result[0]
        except IndexError:
            return result
    match name:
        case str():
            logger.debug(f"Looking up reagent type by name: {name}")
            query = query.filter(models.ReagentType.name==name)
            limit = 1
        case _:
            pass
    return query_return(query=query, limit=limit)

def lookup_submissions(ctx:Settings,
                       submission_type:str|models.SubmissionType|None=None,
                       id:int|str|None=None,
                       rsl_number:str|None=None,
                       start_date:date|str|int|None=None,
                       end_date:date|str|int|None=None,
                       reagent:models.Reagent|str|None=None,
                       chronologic:bool=False, limit:int=0, 
                       **kwargs
                       ) -> models.BasicSubmission | List[models.BasicSubmission]:
    if submission_type == None:
        model = models.BasicSubmission.find_subclasses(ctx=ctx, attrs=kwargs)
    else:
        if isinstance(submission_type, models.SubmissionType):
            model = models.BasicSubmission.find_subclasses(ctx=ctx, submission_type=submission_type.name)
        else:
            model = models.BasicSubmission.find_subclasses(ctx=ctx, submission_type=submission_type)
    query = setup_lookup(ctx=ctx, locals=locals()).query(model)
    # by submission type
    match submission_type:
        case models.SubmissionType():
            logger.debug(f"Looking up BasicSubmission with submission type: {submission_type}")
            # query = query.filter(models.BasicSubmission.submission_type_name==submission_type.name)
            query = query.filter(model.submission_type_name==submission_type.name)
        case str():
            logger.debug(f"Looking up BasicSubmission with submission type: {submission_type}")
            # query = query.filter(models.BasicSubmission.submission_type_name==submission_type)
            query = query.filter(model.submission_type_name==submission_type)
        case _:
            pass
    # by date range
    if start_date != None and end_date == None:
        logger.warning(f"Start date with no end date, using today.")
        end_date = date.today()
    if end_date != None and start_date == None:
        logger.warning(f"End date with no start date, using Jan 1, 2023")
        start_date = date(2023, 1, 1)
    if start_date != None:
        match start_date:
            case date():
                start_date = start_date.strftime("%Y-%m-%d")
            case int():
                start_date = datetime.fromordinal(datetime(1900, 1, 1).toordinal() + start_date - 2).date().strftime("%Y-%m-%d")
            case _:
                start_date = parse(start_date).strftime("%Y-%m-%d")
        match end_date:
            case date():
                end_date = end_date.strftime("%Y-%m-%d")
            case int():
                end_date = datetime.fromordinal(datetime(1900, 1, 1).toordinal() + end_date - 2).date().strftime("%Y-%m-%d")
            case _:
                end_date = parse(end_date).strftime("%Y-%m-%d")
        logger.debug(f"Looking up BasicSubmissions from start date: {start_date} and end date: {end_date}")
        # query = query.filter(models.BasicSubmission.submitted_date.between(start_date, end_date))
        query = query.filter(model.submitted_date.between(start_date, end_date))
    # by reagent (for some reason)
    match reagent:
        case str():
            logger.debug(f"Looking up BasicSubmission with reagent: {reagent}")
            reagent = lookup_reagents(ctx=ctx, lot_number=reagent)
            query = query.join(models.submissions.reagents_submissions).filter(models.submissions.reagents_submissions.c.reagent_id==reagent.id).all()
        case models.Reagent:
            logger.debug(f"Looking up BasicSubmission with reagent: {reagent}")
            query = query.join(models.submissions.reagents_submissions).filter(models.submissions.reagents_submissions.c.reagent_id==reagent.id).all()
        case _:
            pass
    # by rsl number (returns only a single value)
    match rsl_number:
        case str():
            # query = query.filter(models.BasicSubmission.rsl_plate_num==rsl_number)
            query = query.filter(model.rsl_plate_num==rsl_number)
            logger.debug(f"At this point the query gets: {query.all()}")
            limit = 1
        case _:
            pass
    # by id (returns only a single value)
    match id:
        case int():
            logger.debug(f"Looking up BasicSubmission with id: {id}")
            # query = query.filter(models.BasicSubmission.id==id)
            query = query.filter(model.id==id)
            limit = 1
        case str():
            logger.debug(f"Looking up BasicSubmission with id: {id}")
            # query = query.filter(models.BasicSubmission.id==int(id))
            query = query.filter(model.id==int(id))
            limit = 1
        case _:
            pass
    for k, v in kwargs.items():
        attr = getattr(model, k)
        logger.debug(f"Got attr: {attr}")
        query = query.filter(attr==v)
    if len(kwargs) > 0:
        limit = 1
    if chronologic:
        # query.order_by(models.BasicSubmission.submitted_date)
        query.order_by(model.submitted_date)
    # logger.debug(f"At the end of the search, the query gets: {query.all()}")
    return query_return(query=query, limit=limit)

def lookup_submission_type(ctx:Settings,
                           name:str|None=None,
                           limit:int=0
                           ) -> models.SubmissionType|List[models.SubmissionType]:
    query = setup_lookup(ctx=ctx, locals=locals()).query(models.SubmissionType)
    match name:
        case str():
            logger.debug(f"Looking up submission type by name: {name}")
            query = query.filter(models.SubmissionType.name==name)
            limit = 1
        case _:
            pass
    return query_return(query=query, limit=limit)

def lookup_organizations(ctx:Settings,
                name:str|None=None,
                limit:int=0,
                ) -> models.Organization|List[models.Organization]:
    query = setup_lookup(ctx=ctx, locals=locals()).query(models.Organization)
    match name:
        case str():
            logger.debug(f"Looking up organization with name: {name}")
            query = query.filter(models.Organization.name==name)
            limit = 1
        case _:
            pass
    return query_return(query=query, limit=limit)

def lookup_discounts(ctx:Settings,
                    organization:models.Organization|str|int,
                    kit_type:models.KitType|str|int,
                    ) -> models.Discount|List[models.Discount]:
    query = setup_lookup(ctx=ctx, locals=locals()).query(models.Discount)
    match organization:
        case models.Organization():
            logger.debug(f"Looking up discount with organization: {organization}")
            organization = organization.id
        case str():
            logger.debug(f"Looking up discount with organization: {organization}")
            organization = lookup_organizations(ctx=ctx, name=organization).id
        case int():
            logger.debug(f"Looking up discount with organization id: {organization}")
            pass
        case _:
            raise ValueError(f"Invalid value for organization: {organization}")
    match kit_type:
        case models.KitType():
            logger.debug(f"Looking up discount with kit type: {kit_type}")
            kit_type = kit_type.id
        case str():
            logger.debug(f"Looking up discount with kit type: {kit_type}")
            kit_type = lookup_kit_types(ctx=ctx, name=kit_type).id
        case int():
            logger.debug(f"Looking up discount with kit type id: {organization}")
            pass
        case _:
            raise ValueError(f"Invalid value for kit type: {kit_type}")
    return query.join(models.KitType).join(models.Organization).filter(and_(
        models.KitType.id==kit_type, 
        models.Organization.id==organization
        )).all()

def lookup_controls(ctx:Settings,
                    control_type:models.ControlType|str|None=None,
                    start_date:date|str|int|None=None,
                    end_date:date|str|int|None=None,
                    control_name:str|None=None,
                    limit:int=0
                    ) -> models.Control|List[models.Control]:
    query = setup_lookup(ctx=ctx, locals=locals()).query(models.Control)
    # by control type
    match control_type:
        case models.ControlType():
            logger.debug(f"Looking up control by control type: {control_type}")
            query = query.join(models.ControlType).filter(models.ControlType==control_type)
        case str():
            logger.debug(f"Looking up control by control type: {control_type}")
            query = query.join(models.ControlType).filter(models.ControlType.name==control_type)
        case _:
            pass
    # by date range
    if start_date != None and end_date == None:
        logger.warning(f"Start date with no end date, using today.")
        end_date = date.today()
    if end_date != None and start_date == None:
        logger.warning(f"End date with no start date, using Jan 1, 2023")
        start_date = date(2023, 1, 1)
    if start_date != None:
        match start_date:
            case date():
                start_date = start_date.strftime("%Y-%m-%d")
            case int():
                start_date = datetime.fromordinal(datetime(1900, 1, 1).toordinal() + start_date - 2).date().strftime("%Y-%m-%d")
            case _:
                start_date = parse(start_date).strftime("%Y-%m-%d")
        match end_date:
            case date():
                end_date = end_date.strftime("%Y-%m-%d")
            case int():
                end_date = datetime.fromordinal(datetime(1900, 1, 1).toordinal() + end_date - 2).date().strftime("%Y-%m-%d")
            case _:
                end_date = parse(end_date).strftime("%Y-%m-%d")
        logger.debug(f"Looking up BasicSubmissions from start date: {start_date} and end date: {end_date}")
        query = query.filter(models.Control.submitted_date.between(start_date, end_date))
    match control_name:
        case str():
            query = query.filter(models.Control.name.startswith(control_name))
            limit = 1
        case _:
            pass
    return query_return(query=query, limit=limit)
    
def lookup_control_types(ctx:Settings, limit:int=0) -> models.ControlType|List[models.ControlType]:
    query = setup_lookup(ctx=ctx, locals=locals()).query(models.ControlType)
    return query_return(query=query, limit=limit)

def lookup_samples(ctx:Settings,
                   submitter_id:str|None=None,
                   sample_type:str|None=None,
                   limit:int=0,
                   **kwargs
                   ) -> models.BasicSample|models.WastewaterSample|List[models.BasicSample]:
    logger.debug(f"Length of kwargs: {len(kwargs)}")
    # model = models.find_subclasses(parent=models.BasicSample, attrs=kwargs)
    model = models.BasicSample.find_subclasses(ctx=ctx, attrs=kwargs)
    query = setup_lookup(ctx=ctx, locals=locals()).query(model)
    match submitter_id:
        case str():
            logger.debug(f"Looking up {model} with submitter id: {submitter_id}")
            query = query.filter(models.BasicSample.submitter_id==submitter_id)
            limit = 1
        case _:
            pass
    match sample_type:
        case str():
            logger.debug(f"Looking up {model} with sample type: {sample_type}")
            query = query.filter(models.BasicSample.sample_type==sample_type)
        case _:
            pass
    for k, v in kwargs.items():
        attr = getattr(model, k)
        logger.debug(f"Got attr: {attr}")
        query = query.filter(attr==v)
    if len(kwargs) > 0:
        limit = 1
    return query_return(query=query, limit=limit)

def lookup_reagenttype_kittype_association(ctx:Settings,
                                           kit_type:models.KitType|str|None,
                                           reagent_type:models.ReagentType|str|None,
                                           limit:int=0
                                           ) -> models.KitTypeReagentTypeAssociation|List[models.KitTypeReagentTypeAssociation]:
    query = setup_lookup(ctx=ctx, locals=locals()).query(models.KitTypeReagentTypeAssociation)
    match kit_type:
        case models.KitType():
            query = query.filter(models.KitTypeReagentTypeAssociation.kit_type==kit_type)
        case str():
            query = query.join(models.KitType).filter(models.KitType.name==kit_type)
        case _:
            pass
    match reagent_type:
        case models.ReagentType():
            query = query.filter(models.KitTypeReagentTypeAssociation.reagent_type==reagent_type)
        case str():
            query = query.join(models.ReagentType).filter(models.ReagentType.name==reagent_type)
        case _:
            pass
    if kit_type != None and reagent_type != None:
        limit = 1
    return query_return(query=query, limit=limit)

def lookup_submission_sample_association(ctx:Settings,
                                         submission:models.BasicSubmission|str|None=None,
                                         sample:models.BasicSample|str|None=None,
                                         row:int=0,
                                         column:int=0,
                                         limit:int=0,
                                         chronologic:bool=False
                                         ) -> models.SubmissionSampleAssociation|List[models.SubmissionSampleAssociation]:
    query = setup_lookup(ctx=ctx, locals=locals()).query(models.SubmissionSampleAssociation)
    match submission:
        case models.BasicSubmission():
            query = query.filter(models.SubmissionSampleAssociation.submission==submission)
        case str():
            query = query.join(models.BasicSubmission).filter(models.BasicSubmission.rsl_plate_num==submission)
        case _:
            pass
    match sample:
        case models.BasicSample():
            query = query.filter(models.SubmissionSampleAssociation.sample==sample)
        case str():
            query = query.join(models.BasicSample).filter(models.BasicSample.submitter_id==sample)
        case _:
            pass
    if row > 0:
        query = query.filter(models.SubmissionSampleAssociation.row==row)
    if column > 0:
        query = query.filter(models.SubmissionSampleAssociation.column==column)
    logger.debug(f"Query count: {query.count()}")
    if chronologic:
        query.join(models.BasicSubmission).order_by(models.BasicSubmission.submitted_date)
    if query.count() <= 1:
        limit = 1
    return query_return(query=query, limit=limit)

def lookup_modes(ctx:Settings) -> List[str]:
    rel = ctx.database_session.query(models.Control).first()
    try:
        cols = [item.name for item in list(rel.__table__.columns) if isinstance(item.type, JSON)]
    except AttributeError as e:
        logger.debug(f"Failed to get available modes from db: {e}")
        cols = []
    return cols

############### Complex Lookups ###################################

def lookup_sub_samp_association_by_plate_sample(ctx:Settings, rsl_plate_num:str|models.BasicSample, rsl_sample_num:str|models.BasicSubmission) -> models.WastewaterAssociation:
    """
    _summary_

    Args:
        ctx (Settings): _description_
        rsl_plate_num (str): _description_
        sample_submitter_id (_type_): _description_

    Returns:
        models.SubmissionSampleAssociation: _description_
    """    
    # logger.debug(f"{type(rsl_plate_num)}, {type(rsl_sample_num)}")
    match rsl_plate_num:
        case models.BasicSubmission()|models.Wastewater():
            # logger.debug(f"Model for rsl_plate_num: {rsl_plate_num}")
            first_query = ctx.database_session.query(models.SubmissionSampleAssociation)\
                .filter(models.SubmissionSampleAssociation.submission==rsl_plate_num)
        case str():
            # logger.debug(f"String for rsl_plate_num: {rsl_plate_num}")
            first_query = ctx.database_session.query(models.SubmissionSampleAssociation)\
                .join(models.BasicSubmission)\
                .filter(models.BasicSubmission.rsl_plate_num==rsl_plate_num)
        case _:
            logger.error(f"Unknown case for rsl_plate_num {rsl_plate_num}")
    match rsl_sample_num:
        case models.BasicSample()|models.WastewaterSample():
            # logger.debug(f"Model for rsl_sample_num: {rsl_sample_num}")
            second_query = first_query.filter(models.SubmissionSampleAssociation.sample==rsl_sample_num)
        # case models.WastewaterSample:
        #     second_query = first_query.filter(models.SubmissionSampleAssociation.sample==rsl_sample_num)
        case str():
            # logger.debug(f"String for rsl_sample_num: {rsl_sample_num}")
            second_query = first_query.join(models.BasicSample)\
                .filter(models.BasicSample.submitter_id==rsl_sample_num)
        case _:
            logger.error(f"Unknown case for rsl_sample_num {rsl_sample_num}")
    try:
        return second_query.first()
    except UnboundLocalError:
        logger.error(f"Couldn't construct second query")
        return None