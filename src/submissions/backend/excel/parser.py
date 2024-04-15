'''
contains parser object for pulling values from client generated submission sheets.
'''
from getpass import getuser
from pprint import pformat
from typing import List
import pandas as pd
import numpy as np
from pathlib import Path
from backend.db.models import *
from backend.validators import PydSubmission, PydReagent, RSLNamer, PydSample, PydEquipment
import logging, re
from collections import OrderedDict
from datetime import date
from dateutil.parser import parse, ParserError
from tools import check_not_nan, convert_nans_to_nones, row_map, is_missing

logger = logging.getLogger(f"submissions.{__name__}")

row_keys = {v:k for k,v in row_map.items()}

class SheetParser(object):
    """
    object to pull and contain data from excel file
    """
    def __init__(self, filepath:Path|None = None):
        """
        Args:
            filepath (Path | None, optional): file path to excel sheet. Defaults to None.
        """        
        logger.debug(f"\n\nParsing {filepath.__str__()}\n\n")
        match filepath:
            case Path():
                self.filepath = filepath
            case str():
                self.filepath = Path(filepath)
            case _:
                logger.error(f"No filepath given.")
                raise ValueError("No filepath given.")
        try:
            self.xl = pd.ExcelFile(filepath)
        except ValueError as e:
            logger.error(f"Incorrect value: {e}")
            raise FileNotFoundError(f"Couldn't parse file {self.filepath}")
        self.sub = OrderedDict()
        # make decision about type of sample we have
        self.sub['submission_type'] = dict(value=RSLNamer.retrieve_submission_type(filename=self.filepath), missing=True)
        # # grab the info map from the submission type in database
        self.parse_info()
        self.import_kit_validation_check()
        self.parse_reagents()
        self.import_reagent_validation_check()
        self.parse_samples()
        self.parse_equipment()
        self.finalize_parse()
        logger.debug(f"Parser.sub after info scrape: {pformat(self.sub)}")
                
    def parse_info(self):
        """
        Pulls basic information from the excel sheet
        """        
        parser = InfoParser(xl=self.xl, submission_type=self.sub['submission_type']['value'])
        info = parser.parse_info() 
        self.info_map = parser.map
        for k,v in info.items():
            match k:
                case "sample":
                    pass
                case _:
                    self.sub[k] = v
        
    def parse_reagents(self, extraction_kit:str|None=None):
        """
        Pulls reagent info from the excel sheet

        Args:
            extraction_kit (str | None, optional): Relevant extraction kit for reagent map. Defaults to None.
        """        
        if extraction_kit == None:
            extraction_kit = extraction_kit=self.sub['extraction_kit']
        # logger.debug(f"Parsing reagents for {extraction_kit}")
        self.sub['reagents'] = ReagentParser(xl=self.xl, submission_type=self.sub['submission_type'], extraction_kit=extraction_kit).parse_reagents()

    def parse_samples(self):
        """
        Pulls sample info from the excel sheet
        """        
        parser = SampleParser(xl=self.xl, submission_type=self.sub['submission_type']['value'])
        self.sample_result, self.sub['samples'] = parser.parse_samples()
        self.plate_map = parser.plate_map

    def parse_equipment(self):
        parser = EquipmentParser(xl=self.xl, submission_type=self.sub['submission_type']['value'])
        self.sub['equipment'] = parser.parse_equipment()

    def import_kit_validation_check(self):
        """
        Enforce that the parser has an extraction kit
        """    
        from frontend.widgets.pop_ups import KitSelector
        if not check_not_nan(self.sub['extraction_kit']['value']):
            dlg = KitSelector(title="Kit Needed", message="At minimum a kit is needed. Please select one.")
            if dlg.exec():
                self.sub['extraction_kit'] = dict(value=dlg.getValues(), missing=True)
            else:
                raise ValueError("Extraction kit needed.")
        else:
            if isinstance(self.sub['extraction_kit'], str):
                self.sub['extraction_kit'] = dict(value=self.sub['extraction_kit'], missing=True)

    def import_reagent_validation_check(self):
        """
        Enforce that only allowed reagents get into the Pydantic Model
        """          
        kit = KitType.query(name=self.sub['extraction_kit']['value'])
        allowed_reagents = [item.name for item in kit.get_reagents()]
        # logger.debug(f"List of reagents for comparison with allowed_reagents: {pformat(self.sub['reagents'])}")
        self.sub['reagents'] = [reagent for reagent in self.sub['reagents'] if reagent.type in allowed_reagents]

    def finalize_parse(self):
        """
        Run custom final validations of data for submission subclasses.
        """        
        finisher = BasicSubmission.find_polymorphic_subclass(polymorphic_identity=self.sub['submission_type']).finalize_parse
        self.sub = finisher(input_dict=self.sub, xl=self.xl, info_map=self.info_map, plate_map=self.plate_map)

    def to_pydantic(self) -> PydSubmission:
        """
        Generates a pydantic model of scraped data for validation

        Returns:
            PydSubmission: output pydantic model
        """       
        # logger.debug(f"Submission dictionary coming into 'to_pydantic':\n{pformat(self.sub)}")
        logger.debug(f"Equipment: {self.sub['equipment']}")
        if len(self.sub['equipment']) == 0:
            self.sub['equipment'] = None
        psm = PydSubmission(filepath=self.filepath, **self.sub)
        return psm
    
class InfoParser(object):

    def __init__(self, xl:pd.ExcelFile, submission_type:str):
        logger.info(f"\n\Hello from InfoParser!\n\n")
        self.map = self.fetch_submission_info_map(submission_type=submission_type)
        self.xl = xl
        logger.debug(f"Info map for InfoParser: {pformat(self.map)}")
        
    def fetch_submission_info_map(self, submission_type:str|dict) -> dict:
        """
        Gets location of basic info from the submission_type object in the database.

        Args:
            submission_type (str|dict): name of the submission type or parsed object with value=submission_type

        Returns:
            dict: Location map of all info for this submission type
        """        
        if isinstance(submission_type, str):
            submission_type = dict(value=submission_type, missing=True)
        logger.debug(f"Looking up submission type: {submission_type['value']}")
        submission_type = SubmissionType.query(name=submission_type['value'])
        info_map = submission_type.info_map
        # Get the parse_info method from the submission type specified
        self.custom_parser = BasicSubmission.find_polymorphic_subclass(polymorphic_identity=submission_type.name).parse_info
        return info_map

    def parse_info(self) -> dict:
        """
        Pulls basic info from the excel sheet.

        Returns:
            dict: key:value of basic info
        """        
        dicto = {}
        for sheet in self.xl.sheet_names:
            df = self.xl.parse(sheet, header=None)
            relevant = {}
            for k, v in self.map.items():
                if isinstance(v, str):
                    dicto[k] = dict(value=v, missing=False)
                    continue
                if k in ["samples", "all_sheets"]:
                    continue
                if sheet in self.map[k]['sheets']:
                    relevant[k] = v
            logger.debug(f"relevant map for {sheet}: {pformat(relevant)}")
            if relevant == {}:
                continue
            for item in relevant:
                value = df.iat[relevant[item]['row']-1, relevant[item]['column']-1]
                match item:
                    case "submission_type":
                        value, missing = is_missing(value)
                        value = value.title()
                    case _:
                        value, missing = is_missing(value)
                logger.debug(f"Setting {item} on {sheet} to {value}")
                try:
                    dicto[item] = dict(value=value, missing=missing)
                except (KeyError, IndexError):
                    continue
        return self.custom_parser(input_dict=dicto, xl=self.xl)
                
class ReagentParser(object):

    def __init__(self, xl:pd.ExcelFile, submission_type:str, extraction_kit:str):
        logger.debug("\n\nHello from ReagentParser!\n\n")
        self.map = self.fetch_kit_info_map(extraction_kit=extraction_kit, submission_type=submission_type)
        logger.debug(f"Reagent Parser map: {self.map}")
        self.xl = xl

    def fetch_kit_info_map(self, extraction_kit:dict, submission_type:str) -> dict:
        """
        Gets location of kit reagents from database

        Args:
            extraction_kit (dict): Relevant kit information.
            submission_type (str): Name of submission type.

        Returns:
            dict: locations of reagent info for the kit.
        """        
        if isinstance(extraction_kit, dict):
            extraction_kit = extraction_kit['value']
        kit = KitType.query(name=extraction_kit)
        if isinstance(submission_type, dict):
            submission_type = submission_type['value']
        reagent_map = kit.construct_xl_map_for_use(submission_type.title())
        del reagent_map['info']
        return reagent_map
    
    def parse_reagents(self) -> List[PydReagent]:
        """
        Extracts reagent information from the excel form.

        Returns:
            List[PydReagent]: List of parsed reagents.
        """        
        listo = []
        for sheet in self.xl.sheet_names:
            df = self.xl.parse(sheet, header=None, dtype=object)
            df.replace({np.nan: None}, inplace = True)
            relevant = {k.strip():v for k,v in self.map.items() if sheet in self.map[k]['sheet']}
            logger.debug(f"relevant map for {sheet}: {pformat(relevant)}")
            if relevant == {}:
                continue
            for item in relevant:
                logger.debug(f"Attempting to scrape: {item}")
                try:
                    name = df.iat[relevant[item]['name']['row']-1, relevant[item]['name']['column']-1]
                    lot = df.iat[relevant[item]['lot']['row']-1, relevant[item]['lot']['column']-1]
                    expiry = df.iat[relevant[item]['expiry']['row']-1, relevant[item]['expiry']['column']-1]
                    if 'comment' in relevant[item].keys():
                        comment = df.iat[relevant[item]['comment']['row']-1, relevant[item]['comment']['column']-1]
                    else:
                        comment = ""
                except (KeyError, IndexError):
                    listo.append(PydReagent(type=item.strip(), lot=None, expiry=None, name=None, comment="", missing=True))
                    continue
                # If the cell is blank tell the PydReagent
                if check_not_nan(lot):
                    missing = False
                else:
                    missing = True
                # logger.debug(f"Got lot for {item}-{name}: {lot} as {type(lot)}")
                lot = str(lot)
                logger.debug(f"Going into pydantic: name: {name}, lot: {lot}, expiry: {expiry}, type: {item.strip()}, comment: {comment}")
                try:
                    check = name.lower() != "not applicable"
                except AttributeError:
                    check = True
                if check:
                    listo.append(PydReagent(type=item.strip(), lot=lot, expiry=expiry, name=name, comment=comment, missing=missing))
        return listo

class SampleParser(object):
    """
    object to pull data for samples in excel sheet and construct individual sample objects
    """

    def __init__(self, xl:pd.ExcelFile, submission_type:str, sample_map:dict|None=None) -> None:
        """
        convert sample sub-dataframe to dictionary of records

        Args:
            df (pd.DataFrame): input sample dataframe
            elution_map (pd.DataFrame | None, optional): optional map of elution plate. Defaults to None.
        """        
        logger.debug("\n\nHello from SampleParser!\n\n")
        self.samples = []
        self.xl = xl
        self.submission_type = submission_type
        sample_info_map = self.fetch_sample_info_map(submission_type=submission_type, sample_map=sample_map)
        logger.debug(f"sample_info_map: {sample_info_map}")
        self.plate_map = self.construct_plate_map(plate_map_location=sample_info_map['plate_map'])
        logger.debug(f"plate_map: {self.plate_map}")
        self.lookup_table = self.construct_lookup_table(lookup_table_location=sample_info_map['lookup_table'])
        if "plates" in sample_info_map:
            self.plates = sample_info_map['plates']
        self.excel_to_db_map = sample_info_map['xl_db_translation']
        self.create_basic_dictionaries_from_plate_map()
        if isinstance(self.lookup_table, pd.DataFrame):
            self.parse_lookup_table()
        
    def fetch_sample_info_map(self, submission_type:str, sample_map:dict|None=None) -> dict:
        """
        Gets info locations in excel book for submission type.

        Args:
            submission_type (str): submission type

        Returns:
            dict: Info locations.
        """        
        logger.debug(f"Looking up submission type: {submission_type}")
        submission_type = SubmissionType.query(name=submission_type)
        logger.debug(f"info_map: {pformat(submission_type.info_map)}")
        if sample_map is None:
            sample_info_map = submission_type.info_map['samples']
        else:
            sample_info_map = sample_map
        self.custom_sub_parser = BasicSubmission.find_polymorphic_subclass(polymorphic_identity=submission_type.name).parse_samples
        self.custom_sample_parser = BasicSample.find_polymorphic_subclass(polymorphic_identity=f"{submission_type.name} Sample").parse_sample
        return sample_info_map

    def construct_plate_map(self, plate_map_location:dict) -> pd.DataFrame:
        """
        Gets location of samples from plate map grid in excel sheet.

        Args:
            plate_map_location (dict): sheet name, start/end row/column

        Returns:
            pd.DataFrame: Plate map grid
        """        
        logger.debug(f"Plate map location: {plate_map_location}")
        df = self.xl.parse(plate_map_location['sheet'], header=None, dtype=object)
        df = df.iloc[plate_map_location['start_row']-1:plate_map_location['end_row'], plate_map_location['start_column']-1:plate_map_location['end_column']]
        df = pd.DataFrame(df.values[1:], columns=df.iloc[0])
        df = df.set_index(df.columns[0])
        logger.debug(f"Vanilla platemap: {df}")
        custom_mapper = BasicSubmission.find_polymorphic_subclass(polymorphic_identity=self.submission_type)
        df = custom_mapper.custom_platemap(self.xl, df)
        logger.debug(f"Custom platemap:\n{df}")
        return df
    
    def construct_lookup_table(self, lookup_table_location:dict) -> pd.DataFrame:
        """
        Gets table of misc information from excel book

        Args:
            lookup_table_location (dict): sheet name, start/end row

        Returns:
            pd.DataFrame: _description_
        """        
        try:
            df = self.xl.parse(lookup_table_location['sheet'], header=None, dtype=object)
        except KeyError:
            return None
        df = df.iloc[lookup_table_location['start_row']-1:lookup_table_location['end_row']]
        df = pd.DataFrame(df.values[1:], columns=df.iloc[0])
        df = df.reset_index(drop=True)
        return df
    
    def create_basic_dictionaries_from_plate_map(self):
        """
        Parse sample location/name from plate map
        """        
        invalids = [0, "0", "EMPTY"]
        new_df = self.plate_map.dropna(axis=1, how='all')
        columns = new_df.columns.tolist()
        for _, iii in new_df.iterrows():
            for c in columns:
                if check_not_nan(iii[c]):
                    if iii[c] in invalids:
                        logger.debug(f"Invalid sample name: {iii[c]}, skipping.")
                        continue
                    id = iii[c]
                    logger.debug(f"Adding sample {iii[c]}")
                    try:
                        c = self.plate_map.columns.get_loc(c) + 1
                    except Exception as e:
                        logger.error(f"Unable to get column index of {c} due to {e}")
                    self.samples.append(dict(submitter_id=id, row=row_keys[iii._name], column=c))
    
    def parse_lookup_table(self):
        """
        Parse misc info from lookup table.
        """        
        def determine_if_date(input_str) -> str|date:
            regex = re.compile(r"^\d{4}-?\d{2}-?\d{2}")
            if bool(regex.search(input_str)):
                logger.warning(f"{input_str} is a date!")
                try:
                    return parse(input_str)
                except ParserError:
                    return None
            else:
                return input_str
        for sample in self.samples:
            addition = self.lookup_table[self.lookup_table.isin([sample['submitter_id']]).any(axis=1)].squeeze()
            # logger.debug(addition)
            if isinstance(addition, pd.DataFrame) and not addition.empty:
                addition = addition.iloc[0]
            # logger.debug(f"Lookuptable info: {addition.to_dict()}")
            for k,v in addition.to_dict().items():
                # logger.debug(f"Checking {k} in lookup table.")
                if check_not_nan(k) and isinstance(k, str):
                    if k.lower() not in sample:
                        k = k.replace(" ", "_").replace("#","num").lower()
                        # logger.debug(f"Adding {type(v)} - {k}, {v} to the lookuptable output dict")
                        match v:
                            case pd.Timestamp():
                                sample[k] = v.date()
                            case str():
                                sample[k] = determine_if_date(v)
                            case _:
                                sample[k] = v
            # Set row in lookup table to blank values to prevent multipe lookups.
            try:
                self.lookup_table.loc[self.lookup_table['Sample #']==addition['Sample #']] = np.nan
            except (ValueError, KeyError):
                pass
            try:
                self.lookup_table.loc[self.lookup_table['Well']==addition['Well']] = np.nan
            except (ValueError, KeyError):
                pass
            # logger.debug(f"Output sample dict: {sample}")
        logger.debug(f"Final lookup_table: \n\n {self.lookup_table}")

    def parse_samples(self) -> List[dict]|List[BasicSample]:
        """
        Parse merged platemap\lookup info into dicts/samples

        Returns:
            List[dict]|List[models.BasicSample]: List of samples
        """        
        result = None
        new_samples = []
        logger.debug(f"Starting samples: {pformat(self.samples)}")
        for sample in self.samples:
            translated_dict = {}
            for k, v in sample.items():
                match v:
                    case dict():
                        v = None
                    case float():
                        v = convert_nans_to_nones(v)
                    case _:
                        v = v
                try:
                    translated_dict[self.excel_to_db_map[k]] = convert_nans_to_nones(v)
                except KeyError:
                    translated_dict[k] = convert_nans_to_nones(v)
            translated_dict['sample_type'] = f"{self.submission_type} Sample"
            translated_dict = self.custom_sub_parser(translated_dict)
            translated_dict = self.custom_sample_parser(translated_dict)
            # logger.debug(f"Here is the output of the custom parser:\n{translated_dict}")
            new_samples.append(PydSample(**translated_dict))
        return result, new_samples

    def grab_plates(self) -> List[str]:
        """
        Parse plate names from 

        Returns:
            List[str]: list of plate names.
        """        
        plates = []
        for plate in self.plates:
            df = self.xl.parse(plate['sheet'], header=None)
            if isinstance(df.iat[plate['row']-1, plate['column']-1], str):
                output = RSLNamer.retrieve_rsl_number(filename=df.iat[plate['row']-1, plate['column']-1])
            else:
                continue
            plates.append(output)
        return plates
    
class EquipmentParser(object):

    def __init__(self, xl:pd.ExcelFile, submission_type:str) -> None:
        self.submission_type = submission_type
        self.xl = xl
        self.map = self.fetch_equipment_map()

    def fetch_equipment_map(self) -> List[dict]:
        """
        Gets the map of equipment locations in the submission type's spreadsheet

        Returns:
            List[dict]: List of locations
        """        
        submission_type = SubmissionType.query(name=self.submission_type)
        return submission_type.construct_equipment_map()
    
    def get_asset_number(self, input:str) -> str:
        """
        Pulls asset number from string.

        Args:
            input (str): String to be scraped

        Returns:
            str: asset number
        """        
        regex = Equipment.get_regex()
        logger.debug(f"Using equipment regex: {regex} on {input}")
        try:
            return regex.search(input).group().strip("-")
        except AttributeError:
            return input
    
    def parse_equipment(self) -> List[PydEquipment]:
        """
        Scrapes equipment from xl sheet

        Returns:
            List[PydEquipment]: list of equipment
        """        
        logger.debug(f"Equipment parser going into parsing: {pformat(self.__dict__)}")
        output = []
        # logger.debug(f"Sheets: {sheets}")
        for sheet in self.xl.sheet_names:
            df = self.xl.parse(sheet, header=None, dtype=object)
            try:
                relevant = [item for item in self.map if item['sheet']==sheet]
            except (TypeError, KeyError):
                continue
            # logger.debug(f"Relevant equipment: {pformat(relevant)}")
            previous_asset = ""
            for equipment in relevant:
                asset = df.iat[equipment['name']['row']-1, equipment['name']['column']-1]
                if not check_not_nan(asset):
                    asset = previous_asset
                else:
                    previous_asset = asset
                asset = self.get_asset_number(input=asset)
                eq = Equipment.query(asset_number=asset)
                process = df.iat[equipment['process']['row']-1, equipment['process']['column']-1]
                try:
                    output.append(PydEquipment(name=eq.name, processes=[process], role=equipment['role'], asset_number=asset, nickname=eq.nickname))
                except AttributeError:
                    logger.error(f"Unable to add {eq} to PydEquipment list.")
                # logger.debug(f"Here is the output so far: {pformat(output)}")
        return output

class PCRParser(object):
    """
    Object to pull data from Design and Analysis PCR export file.
    """    
    def __init__(self, filepath:Path|None = None) -> None:
        """
        Initializes object.

        Args:
            filepath (Path | None, optional): file to parse. Defaults to None.
        """        
        logger.debug(f"Parsing {filepath.__str__()}")        
        if filepath == None:
            logger.error(f"No filepath given.")
            self.xl = None
        else:
            try:
                self.xl = pd.ExcelFile(filepath.__str__())
            except ValueError as e:
                logger.error(f"Incorrect value: {e}")
                self.xl = None
            except PermissionError:
                logger.error(f"Couldn't get permissions for {filepath.__str__()}. Operation might have been cancelled.")
                return
        self.parse_general(sheet_name="Results")
        namer = RSLNamer(filename=filepath.__str__())
        self.plate_num = namer.parsed_name
        self.submission_type = namer.submission_type
        logger.debug(f"Set plate number to {self.plate_num} and type to {self.submission_type}")
        parser = BasicSubmission.find_polymorphic_subclass(self.submission_type)
        self.samples = parser.parse_pcr(xl=self.xl, rsl_number=self.plate_num)
        
    def parse_general(self, sheet_name:str):
        """
        Parse general info rows for all types of PCR results

        Args:
            sheet_name (str): Name of sheet in excel workbook that holds info.
        """        
        self.pcr = {}
        df = self.xl.parse(sheet_name=sheet_name, dtype=object).fillna("")
        self.pcr['comment'] = df.iloc[0][1]
        self.pcr['operator'] = df.iloc[1][1]
        self.pcr['barcode'] = df.iloc[2][1]
        self.pcr['instrument'] = df.iloc[3][1]
        self.pcr['block_type'] = df.iloc[4][1]
        self.pcr['instrument_name'] = df.iloc[5][1]
        self.pcr['instrument_serial'] = df.iloc[6][1]
        self.pcr['heated_cover_serial'] = df.iloc[7][1]
        self.pcr['block_serial'] = df.iloc[8][1]
        self.pcr['run-start'] = df.iloc[9][1]
        self.pcr['run_end'] = df.iloc[10][1]
        self.pcr['run_duration'] = df.iloc[11][1]
        self.pcr['sample_volume'] = df.iloc[12][1]
        self.pcr['cover_temp'] = df.iloc[13][1]
        self.pcr['passive_ref'] = df.iloc[14][1]
        self.pcr['pcr_step'] = df.iloc[15][1]
        self.pcr['quant_cycle_method'] = df.iloc[16][1]
        self.pcr['analysis_time'] = df.iloc[17][1]
        self.pcr['software'] = df.iloc[18][1]
        self.pcr['plugin'] = df.iloc[19][1]
        self.pcr['exported_on'] = df.iloc[20][1]
        self.pcr['imported_by'] = getuser()
