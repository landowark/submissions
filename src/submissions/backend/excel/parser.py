'''
contains parser object for pulling values from client generated submission sheets.
'''
import sys
from copy import copy
from getpass import getuser
from pprint import pformat
from typing import List
import pandas as pd
from openpyxl import load_workbook, Workbook
from openpyxl.worksheet.protection import SheetProtection
import numpy as np
from pathlib import Path
from backend.db.models import *
from backend.validators import PydSubmission, PydReagent, RSLNamer, PydSample, PydEquipment
import logging, re
from collections import OrderedDict
from datetime import date
from dateutil.parser import parse, ParserError
from tools import check_not_nan, convert_nans_to_nones, row_map, row_keys, is_missing, remove_key_from_list_of_dicts


logger = logging.getLogger(f"submissions.{__name__}")


# row_keys = {v:k for k,v in row_map.items()}

class SheetParser(object):
    """
    object to pull and contain data from excel file
    """

    def __init__(self, filepath: Path | None = None):
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
            self.xl = load_workbook(filepath, data_only=True)
        except ValueError as e:
            logger.error(f"Incorrect value: {e}")
            raise FileNotFoundError(f"Couldn't parse file {self.filepath}")
        self.sub = OrderedDict()
        # NOTE: make decision about type of sample we have
        self.sub['submission_type'] = dict(value=RSLNamer.retrieve_submission_type(filename=self.filepath),
                                           missing=True)
        self.submission_type = SubmissionType.query(name=self.sub['submission_type'])
        self.sub_object = BasicSubmission.find_polymorphic_subclass(polymorphic_identity=self.submission_type)
        # NOTE: grab the info map from the submission type in database
        self.parse_info()
        self.import_kit_validation_check()
        self.parse_reagents()
        self.parse_samples()
        self.parse_equipment()
        self.finalize_parse()
        # logger.debug(f"Parser.sub after info scrape: {pformat(self.sub)}")

    def parse_info(self):
        """
        Pulls basic information from the excel sheet
        """
        parser = InfoParser(xl=self.xl, submission_type=self.submission_type, sub_object=self.sub_object)
        info = parser.parse_info()
        self.info_map = parser.map
        # exclude_from_info = BasicSubmission.find_polymorphic_subclass(polymorphic_identity=self.sub['submission_type']).exclude_from_info_parser()
        for k, v in info.items():
            match k:
                case "sample":
                    # case item if
                    pass
                case _:
                    self.sub[k] = v

    def parse_reagents(self, extraction_kit: str | None = None):
        """
        Pulls reagent info from the excel sheet

        Args:
            extraction_kit (str | None, optional): Relevant extraction kit for reagent map. Defaults to None.
        """
        if extraction_kit == None:
            extraction_kit = self.sub['extraction_kit']
        # logger.debug(f"Parsing reagents for {extraction_kit}")
        self.sub['reagents'] = ReagentParser(xl=self.xl, submission_type=self.submission_type,
                                             extraction_kit=extraction_kit).parse_reagents()

    def parse_samples(self):
        """
        Pulls sample info from the excel sheet
        """
        parser = SampleParser(xl=self.xl, submission_type=self.submission_type)
        self.sub['samples'] = parser.reconcile_samples()
        # self.plate_map = parser.plate_map

    def parse_equipment(self):
        parser = EquipmentParser(xl=self.xl, submission_type=self.submission_type)
        self.sub['equipment'] = parser.parse_equipment()

    def import_kit_validation_check(self):
        """
        Enforce that the parser has an extraction kit
        """
        from frontend.widgets.pop_ups import ObjectSelector
        if 'extraction_kit' not in self.sub.keys() or not check_not_nan(self.sub['extraction_kit']['value']):
            dlg = ObjectSelector(title="Kit Needed", message="At minimum a kit is needed. Please select one.",
                                 obj_type=KitType)
            if dlg.exec():
                self.sub['extraction_kit'] = dict(value=dlg.parse_form(), missing=True)
            else:
                raise ValueError("Extraction kit needed.")
        else:
            if isinstance(self.sub['extraction_kit'], str):
                self.sub['extraction_kit'] = dict(value=self.sub['extraction_kit'], missing=True)

    def finalize_parse(self):
        """
        Run custom final validations of data for submission subclasses.
        """
        # finisher = BasicSubmission.find_polymorphic_subclass(
        #     polymorphic_identity=self.sub['submission_type']).finalize_parse
        self.sub = self.sub_object.finalize_parse(input_dict=self.sub, xl=self.xl, info_map=self.info_map)

    def to_pydantic(self) -> PydSubmission:
        """
        Generates a pydantic model of scraped data for validation

        Returns:
            PydSubmission: output pydantic model
        """
        # logger.debug(f"Submission dictionary coming into 'to_pydantic':\n{pformat(self.sub)}")
        pyd_dict = copy(self.sub)
        pyd_dict['samples'] = [PydSample(**sample) for sample in self.sub['samples']]
        pyd_dict['reagents'] = [PydReagent(**reagent) for reagent in self.sub['reagents']]
        # logger.debug(f"Equipment: {self.sub['equipment']}")
        try:
            check = len(self.sub['equipment']) == 0
        except TypeError:
            check = True
        if check:
            pyd_dict['equipment'] = None
        else:
            pyd_dict['equipment'] = self.sub['equipment']
        psm = PydSubmission(filepath=self.filepath, **pyd_dict)
        return psm


class InfoParser(object):

    def __init__(self, xl: Workbook, submission_type: str|SubmissionType, sub_object: BasicSubmission|None=None):
        logger.info(f"\n\nHello from InfoParser!\n\n")
        if isinstance(submission_type, str):
            submission_type = SubmissionType.query(name=submission_type)
        if sub_object is None:
            sub_object = BasicSubmission.find_polymorphic_subclass(polymorphic_identity=submission_type.name)
        self.submission_type_obj = submission_type
        self.sub_object = sub_object
        self.map = self.fetch_submission_info_map()
        self.xl = xl
        # logger.debug(f"Info map for InfoParser: {pformat(self.map)}")

    def fetch_submission_info_map(self) -> dict:
        """
        Gets location of basic info from the submission_type object in the database.

        Args:
            submission_type (str|dict): name of the submission type or parsed object with value=submission_type

        Returns:
            dict: Location map of all info for this submission type
        """
        self.submission_type = dict(value=self.submission_type_obj.name, missing=True)
        # logger.debug(f"Looking up submission type: {self.submission_type['value']}")
        info_map = self.sub_object.construct_info_map("read")
        # NOTE: Get the parse_info method from the submission type specified
        return info_map

    def parse_info(self) -> dict:
        """
        Pulls basic info from the excel sheet.

        Returns:
            dict: key:value of basic info
        """
        dicto = {}
        # NOTE: This loop parses generic info
        # logger.debug(f"Map: {self.map}")
        for sheet in self.xl.sheetnames:
            ws = self.xl[sheet]
            relevant = []
            for k, v in self.map.items():
                # NOTE: If the value is hardcoded put it in the dictionary directly.
                if isinstance(v, str):
                    dicto[k] = dict(value=v, missing=False)
                    continue
                # logger.debug(f"Looking for {k} in self.map")
                # logger.debug(f"Locations: {v}")
                for location in v:
                    try:
                        check = location['sheet'] == sheet
                    except TypeError:
                        logger.warning(f"Location is likely a string, skipping")
                        dicto[k] = dict(value=location, missing=False)
                        check = False
                    if check:
                        new = location
                        new['name'] = k
                        relevant.append(new)
            logger.debug(f"relevant map for {sheet}: {pformat(relevant)}")
            if not relevant:
                continue
            for item in relevant:
                # NOTE: Get cell contents at this location
                value = ws.cell(row=item['row'], column=item['column']).value
                logger.debug(f"Value for {item['name']} = {value}")
                match item['name']:
                    case "submission_type":
                        value, missing = is_missing(value)
                        value = value.title()
                    case thing if thing in self.sub_object.jsons():
                        value, missing = is_missing(value)
                        if missing: continue
                        value = dict(name=f"Parser_{sheet}", text=value, time=datetime.now())
                        try:
                            dicto[item['name']]['value'] += value
                            continue
                        except KeyError:
                            logger.error(f"New value for {item['name']}")
                    case _:
                        value, missing = is_missing(value)
                # logger.debug(f"Setting {item} on {sheet} to {value}")
                if item['name'] not in dicto.keys():
                    try:
                        dicto[item['name']] = dict(value=value, missing=missing)
                    except (KeyError, IndexError):
                        continue
        return self.sub_object.custom_info_parser(input_dict=dicto, xl=self.xl)


class ReagentParser(object):

    def __init__(self, xl: Workbook, submission_type: str, extraction_kit: str, sub_object:BasicSubmission|None=None):
        # logger.debug("\n\nHello from ReagentParser!\n\n")
        self.submission_type_obj = submission_type
        self.sub_object = sub_object
        if isinstance(extraction_kit, dict):
            extraction_kit = extraction_kit['value']
        self.kit_object = KitType.query(name=extraction_kit)
        self.map = self.fetch_kit_info_map(extraction_kit=extraction_kit, submission_type=submission_type)
        # logger.debug(f"Reagent Parser map: {self.map}")
        self.xl = xl

    def fetch_kit_info_map(self, extraction_kit: dict, submission_type: str) -> dict:
        """
        Gets location of kit reagents from database

        Args:
            extraction_kit (dict): Relevant kit information.
            submission_type (str): Name of submission type.

        Returns:
            dict: locations of reagent info for the kit.
        """

        if isinstance(submission_type, dict):
            submission_type = submission_type['value']
        reagent_map = self.kit_object.construct_xl_map_for_use(submission_type)
        try:
            del reagent_map['info']
        except KeyError:
            pass
        return reagent_map

    def parse_reagents(self) -> List[PydReagent]:
        """
        Extracts reagent information from the excel form.

        Returns:
            List[PydReagent]: List of parsed reagents.
        """
        listo = []
        for sheet in self.xl.sheetnames:
            ws = self.xl[sheet]
            relevant = {k.strip(): v for k, v in self.map.items() if sheet in self.map[k]['sheet']}
            # logger.debug(f"relevant map for {sheet}: {pformat(relevant)}")
            if relevant == {}:
                continue
            for item in relevant:
                # logger.debug(f"Attempting to scrape: {item}")
                try:
                    reagent = relevant[item]
                    name = ws.cell(row=reagent['name']['row'], column=reagent['name']['column']).value
                    lot = ws.cell(row=reagent['lot']['row'], column=reagent['lot']['column']).value
                    expiry = ws.cell(row=reagent['expiry']['row'], column=reagent['expiry']['column']).value
                    if 'comment' in relevant[item].keys():
                        # logger.debug(f"looking for {relevant[item]} comment.")
                        comment = ws.cell(row=reagent['comment']['row'], column=reagent['comment']['column']).value
                    else:
                        comment = ""
                except (KeyError, IndexError):
                    listo.append(
                        PydReagent(type=item.strip(), lot=None, expiry=None, name=None, comment="", missing=True))
                    continue
                # NOTE: If the cell is blank tell the PydReagent
                if check_not_nan(lot):
                    missing = False
                else:
                    missing = True
                # logger.debug(f"Got lot for {item}-{name}: {lot} as {type(lot)}")
                lot = str(lot)
                # logger.debug(
                #     f"Going into pydantic: name: {name}, lot: {lot}, expiry: {expiry}, type: {item.strip()}, comment: {comment}")
                try:
                    check = name.lower() != "not applicable"
                except AttributeError:
                    logger.warning(f"name is not a string.")
                    check = True
                if check:
                    listo.append(dict(type=item.strip(), lot=lot, expiry=expiry, name=name, comment=comment,
                                            missing=missing))
        return listo


class SampleParser(object):
    """
    object to pull data for samples in excel sheet and construct individual sample objects
    """

    def __init__(self, xl: Workbook, submission_type: SubmissionType, sample_map: dict | None = None, sub_object:BasicSubmission|None=None) -> None:
        """
        convert sample sub-dataframe to dictionary of records

        Args:
            df (pd.DataFrame): input sample dataframe
            elution_map (pd.DataFrame | None, optional): optional map of elution plate. Defaults to None.
        """
        # logger.debug("\n\nHello from SampleParser!\n\n")
        self.samples = []
        self.xl = xl
        if isinstance(submission_type, str):
            submission_type = SubmissionType.query(name=submission_type)
        self.submission_type = submission_type.name
        self.submission_type_obj = submission_type
        if sub_object is None:
            sub_object = BasicSubmission.find_polymorphic_subclass(polymorphic_identity=self.submission_type_obj.name)
        self.sub_object = sub_object
        self.sample_info_map = self.fetch_sample_info_map(submission_type=submission_type, sample_map=sample_map)
        # logger.debug(f"sample_info_map: {self.sample_info_map}")
        self.plate_map_samples = self.parse_plate_map()
        self.lookup_samples = self.parse_lookup_table()

    def fetch_sample_info_map(self, submission_type: str, sample_map: dict | None = None) -> dict:
        """
        Gets info locations in excel book for submission type.

        Args:
            submission_type (str): submission type

        Returns:
            dict: Info locations.
        """
        # logger.debug(f"Looking up submission type: {submission_type}")
        self.sample_type = self.sub_object.get_default_info("sample_type")
        self.samp_object = BasicSample.find_polymorphic_subclass(polymorphic_identity=self.sample_type)
        # logger.debug(f"Got sample class: {self.samp_object.__name__}")
        # logger.debug(f"info_map: {pformat(se)}")
        if sample_map is None:
            sample_info_map = self.sub_object.construct_sample_map()
        else:
            sample_info_map = sample_map
        return sample_info_map

    # def construct_plate_map(self, plate_map_location: dict) -> pd.DataFrame:
    #     """
    #     Gets location of samples from plate map grid in excel sheet.
    #
    #     Args:
    #         plate_map_location (dict): sheet name, start/end row/column
    #
    #     Returns:
    #         pd.DataFrame: Plate map grid
    #     """
    #     logger.debug(f"Plate map location: {plate_map_location}")
    #     df = self.xl.parse(plate_map_location['sheet'], header=None, dtype=object)
    #     df = df.iloc[plate_map_location['start_row'] - 1:plate_map_location['end_row'],
    #          plate_map_location['start_column'] - 1:plate_map_location['end_column']]
    #     df = pd.DataFrame(df.values[1:], columns=df.iloc[0])
    #     df = df.set_index(df.columns[0])
    #     logger.debug(f"Vanilla platemap: {df}")
    #     # custom_mapper = BasicSubmission.find_polymorphic_subclass(polymorphic_identity=self.submission_type)
    #     df = self.sub_object.custom_platemap(self.xl, df)
    #     # logger.debug(f"Custom platemap:\n{df}")
    #     return df
    #
    # def construct_lookup_table(self, lookup_table_location: dict) -> pd.DataFrame:
    #     """
    #     Gets table of misc information from excel book
    #
    #     Args:
    #         lookup_table_location (dict): sheet name, start/end row
    #
    #     Returns:
    #         pd.DataFrame: _description_
    #     """
    #     try:
    #         df = self.xl.parse(lookup_table_location['sheet'], header=None, dtype=object)
    #     except KeyError:
    #         return None
    #     df = df.iloc[lookup_table_location['start_row'] - 1:lookup_table_location['end_row']]
    #     df = pd.DataFrame(df.values[1:], columns=df.iloc[0])
    #     df = df.reset_index(drop=True)
    #     return df

    def parse_plate_map(self):
        """
        Parse sample location/name from plate map
        """
        invalids = [0, "0", "EMPTY"]
        smap = self.sample_info_map['plate_map']
        ws = self.xl[smap['sheet']]
        plate_map_samples = []
        for ii, row in enumerate(range(smap['start_row'], smap['end_row'] + 1), start=1):
            # logger.debug(f"Parsing row: {row}")
            for jj, column in enumerate(range(smap['start_column'], smap['end_column'] + 1), start=1):
                # logger.debug(f"Parsing column: {column}")
                id = str(ws.cell(row=row, column=column).value)
                if check_not_nan(id):
                    if id not in invalids:
                        sample_dict = dict(id=id, row=ii, column=jj)
                        sample_dict['sample_type'] = self.sample_type
                        plate_map_samples.append(sample_dict)
                    else:
                        # logger.error(f"Sample cell ({row}, {column}) has invalid value: {id}.")
                        pass
                else:
                    # logger.error(f"Sample cell ({row}, {column}) has no info: {id}.")
                    pass
        return plate_map_samples

    def parse_lookup_table(self) -> List[dict]:
        """
        Parse misc info from lookup table.
        """
        lmap = self.sample_info_map['lookup_table']
        ws = self.xl[lmap['sheet']]
        lookup_samples = []
        for ii, row in enumerate(range(lmap['start_row'], lmap['end_row']+1), start=1):
            row_dict = {k:ws.cell(row=row, column=v).value for k, v in lmap['sample_columns'].items()}
            try:
                row_dict[lmap['merge_on_id']] = str(row_dict[lmap['merge_on_id']])
            except KeyError:
                pass
            row_dict['sample_type'] = self.sample_type
            row_dict['submission_rank'] = ii
            try:
                check = check_not_nan(row_dict[lmap['merge_on_id']])
            except KeyError:
                check = False
            if check:
                lookup_samples.append(self.samp_object.parse_sample(row_dict))
        return lookup_samples

    def parse_samples(self) -> Tuple[Report | None, List[dict] | List[PydSample]]:
        """
        Parse merged platemap/lookup info into dicts/samples

        Returns:
            List[dict]|List[models.BasicSample]: List of samples
        """
        result = None
        new_samples = []
        # logger.debug(f"Starting samples: {pformat(self.samples)}")
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
                translated_dict[k] = convert_nans_to_nones(v)
            translated_dict['sample_type'] = f"{self.submission_type} Sample"
            translated_dict = self.sub_object.parse_samples(translated_dict)
            translated_dict = self.samp_object.parse_sample(translated_dict)
            # logger.debug(f"Here is the output of the custom parser:\n{translated_dict}")
            new_samples.append(PydSample(**translated_dict))
        return result, new_samples

    def reconcile_samples(self):
        # TODO: Move to pydantic validator?
        if self.plate_map_samples is None or self.lookup_samples is None:
            self.samples = self.lookup_samples or self.plate_map_samples
            return
        samples = []
        merge_on_id = self.sample_info_map['lookup_table']['merge_on_id']
        plate_map_samples = sorted(copy(self.plate_map_samples), key=lambda d: d['id'])
        lookup_samples = sorted(copy(self.lookup_samples), key=lambda d: d[merge_on_id])
        for ii, psample in enumerate(plate_map_samples):
            try:
                check = psample['id'] == lookup_samples[ii][merge_on_id]
            except (KeyError, IndexError):
                check = False
            if check:
                # logger.debug(f"Direct match found for {psample['id']}")
                new = lookup_samples[ii] | psample
                lookup_samples[ii] = {}
            else:
                # logger.warning(f"Match for {psample['id']} not direct, running search.")
                for jj, lsample in enumerate(lookup_samples):
                    try:
                        check = lsample[merge_on_id] == psample['id']
                    except KeyError:
                        check = False
                    if check:
                        new = lsample | psample
                        lookup_samples[jj] = {}
                        break
                    else:
                        new = psample
            try:
                check = new['submitter_id'] is None
            except KeyError:
                check = True
            if check:
                new['submitter_id'] = psample['id']
            new = self.sub_object.parse_samples(new)
            samples.append(new)
        samples = remove_key_from_list_of_dicts(samples, "id")
        return sorted(samples, key=lambda k: (k['row'], k['column']))

class EquipmentParser(object):

    def __init__(self, xl: Workbook, submission_type: str|SubmissionType) -> None:
        if isinstance(submission_type, str):
            submission_type = SubmissionType.query(name=submission_type)

        self.submission_type = submission_type
        self.xl = xl
        self.map = self.fetch_equipment_map()

    def fetch_equipment_map(self) -> List[dict]:
        """
        Gets the map of equipment locations in the submission type's spreadsheet

        Returns:
            List[dict]: List of locations
        """
        # submission_type = SubmissionType.query(name=self.submission_type)
        return self.submission_type.construct_equipment_map()

    def get_asset_number(self, input: str) -> str:
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
        for sheet in self.xl.sheetnames:
            # df = self.xl.parse(sheet, header=None, dtype=object)
            ws = self.xl[sheet]
            try:
                relevant = [item for item in self.map if item['sheet'] == sheet]
            except (TypeError, KeyError):
                continue
            # logger.debug(f"Relevant equipment: {pformat(relevant)}")
            previous_asset = ""
            for equipment in relevant:
                # asset = df.iat[equipment['name']['row']-1, equipment['name']['column']-1]
                asset = ws.cell(equipment['name']['row'], equipment['name']['column'])
                if not check_not_nan(asset):
                    asset = previous_asset
                else:
                    previous_asset = asset
                asset = self.get_asset_number(input=asset)
                eq = Equipment.query(asset_number=asset)
                # process = df.iat[equipment['process']['row']-1, equipment['process']['column']-1]
                process = ws.cell(row=equipment['process']['row'], column=equipment['process']['column'])
                try:
                    output.append(
                        dict(name=eq.name, processes=[process], role=equipment['role'], asset_number=asset,
                                     nickname=eq.nickname))
                except AttributeError:
                    logger.error(f"Unable to add {eq} to PydEquipment list.")
                # logger.debug(f"Here is the output so far: {pformat(output)}")
        return output


# class PCRParser(object):
#     """
#     Object to pull data from Design and Analysis PCR export file.
#     """
#
#     def __init__(self, filepath: Path | None = None) -> None:
#         """
#         Initializes object.
#
#         Args:
#             filepath (Path | None, optional): file to parse. Defaults to None.
#         """
#         logger.debug(f"Parsing {filepath.__str__()}")
#         if filepath == None:
#             logger.error(f"No filepath given.")
#             self.xl = None
#         else:
#             try:
#                 self.xl = pd.ExcelFile(filepath.__str__())
#             except ValueError as e:
#                 logger.error(f"Incorrect value: {e}")
#                 self.xl = None
#             except PermissionError:
#                 logger.error(f"Couldn't get permissions for {filepath.__str__()}. Operation might have been cancelled.")
#                 return
#         self.parse_general(sheet_name="Results")
#         namer = RSLNamer(filename=filepath.__str__())
#         self.plate_num = namer.parsed_name
#         self.submission_type = namer.submission_type
#         logger.debug(f"Set plate number to {self.plate_num} and type to {self.submission_type}")
#         parser = BasicSubmission.find_polymorphic_subclass(polymorphic_identity=self.submission_type)
#         self.samples = parser.parse_pcr(xl=self.xl, rsl_number=self.plate_num)
#
#     def parse_general(self, sheet_name: str):
#         """
#         Parse general info rows for all types of PCR results
#
#         Args:
#             sheet_name (str): Name of sheet in excel workbook that holds info.
#         """
#         self.pcr = {}
#         df = self.xl.parse(sheet_name=sheet_name, dtype=object).fillna("")
#         self.pcr['comment'] = df.iloc[0][1]
#         self.pcr['operator'] = df.iloc[1][1]
#         self.pcr['barcode'] = df.iloc[2][1]
#         self.pcr['instrument'] = df.iloc[3][1]
#         self.pcr['block_type'] = df.iloc[4][1]
#         self.pcr['instrument_name'] = df.iloc[5][1]
#         self.pcr['instrument_serial'] = df.iloc[6][1]
#         self.pcr['heated_cover_serial'] = df.iloc[7][1]
#         self.pcr['block_serial'] = df.iloc[8][1]
#         self.pcr['run-start'] = df.iloc[9][1]
#         self.pcr['run_end'] = df.iloc[10][1]
#         self.pcr['run_duration'] = df.iloc[11][1]
#         self.pcr['sample_volume'] = df.iloc[12][1]
#         self.pcr['cover_temp'] = df.iloc[13][1]
#         self.pcr['passive_ref'] = df.iloc[14][1]
#         self.pcr['pcr_step'] = df.iloc[15][1]
#         self.pcr['quant_cycle_method'] = df.iloc[16][1]
#         self.pcr['analysis_time'] = df.iloc[17][1]
#         self.pcr['software'] = df.iloc[18][1]
#         self.pcr['plugin'] = df.iloc[19][1]
#         self.pcr['exported_on'] = df.iloc[20][1]
#         self.pcr['imported_by'] = getuser()

class PCRParser(object):
    """Object to pull data from Design and Analysis PCR export file."""

    def __init__(self, filepath: Path | None=None, submission: BasicSubmission | None=None) -> None:
        """
         Initializes object.

         Args:
             filepath (Path | None, optional): file to parse. Defaults to None.
         """
        logger.debug(f'Parsing {filepath.__str__()}')
        if filepath is None:
            logger.error('No filepath given.')
            self.xl = None
        else:
            try:
                self.xl = load_workbook(filepath)
            except ValueError as e:
                logger.error(f'Incorrect value: {e}')
                self.xl = None
            except PermissionError:
                logger.error(f'Couldn\'t get permissions for {filepath.__str__()}. Operation might have been cancelled.')
                return None
        if submission is None:
            self.submission_obj = Wastewater
            rsl_plate_num = None
        else:
            self.submission_obj = submission
            rsl_plate_num = self.submission_obj.rsl_plate_num
        self.pcr = self.parse_general()
        self.samples = self.submission_obj.parse_pcr(xl=self.xl, rsl_plate_num=rsl_plate_num)

    def parse_general(self):
        """
        Parse general info rows for all types of PCR results

        Args:
            sheet_name (str): Name of sheet in excel workbook that holds info.
         """
        info_map = self.submission_obj.get_submission_type().sample_map['pcr_general_info']
        sheet = self.xl[info_map['sheet']]
        iter_rows = sheet.iter_rows(min_row=info_map['start_row'], max_row=info_map['end_row'])
        pcr = {row[0].value.lower().replace(' ', '_'): row[1].value for row in iter_rows}
        pcr['imported_by'] = getuser()
        return pcr
