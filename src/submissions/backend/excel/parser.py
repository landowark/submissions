'''
contains parser objects for pulling values from client generated submission sheets.
'''
from copy import copy
from getpass import getuser
from pprint import pformat
from typing import List
from openpyxl import load_workbook, Workbook
from pathlib import Path
from backend.db.models import *
from backend.validators import PydSubmission, PydReagent, RSLNamer, PydSample, PydEquipment, PydTips
import logging, re
from collections import OrderedDict
from tools import check_not_nan, convert_nans_to_nones, is_missing, check_key_or_attr

logger = logging.getLogger(f"submissions.{__name__}")


class SheetParser(object):
    """
    object to pull and contain data from excel file
    """

    def __init__(self, filepath: Path | None = None):
        """
        Args:
            filepath (Path | None, optional): file path to excel sheet. Defaults to None.
        """
        logger.info(f"\n\nParsing {filepath.__str__()}\n\n")
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
        self.parse_tips()
        # self.finalize_parse()
        # logger.debug(f"Parser.sub after info scrape: {pformat(self.sub)}")

    def parse_info(self):
        """
        Pulls basic information from the excel sheet
        """
        parser = InfoParser(xl=self.xl, submission_type=self.submission_type, sub_object=self.sub_object)
        info = parser.parse_info()
        self.info_map = parser.map
        try:
            check = info['submission_type']['value'] not in [None, "None", "", " "]
        except KeyError:
            return
        logger.info(
            f"Checking for updated submission type: {self.submission_type.name} against new: {info['submission_type']['value']}")
        if self.submission_type.name != info['submission_type']['value']:
            # logger.debug(f"info submission type: {info}")
            if check:
                self.submission_type = SubmissionType.query(name=info['submission_type']['value'])
                logger.info(f"Updated self.submission_type to {self.submission_type}. Rerunning parse.")
                self.parse_info()
            else:
                self.submission_type = RSLNamer.retrieve_submission_type(filename=self.filepath)
                self.parse_info()
        for k, v in info.items():
            match k:
                # NOTE: exclude samples.
                case "sample":
                    continue
                case _:
                    self.sub[k] = v

    def parse_reagents(self, extraction_kit: str | None = None):
        """
        Calls reagent parser class to pull info from the excel sheet

        Args:
            extraction_kit (str | None, optional): Relevant extraction kit for reagent map. Defaults to None.
        """
        if extraction_kit is None:
            extraction_kit = self.sub['extraction_kit']
        # logger.debug(f"Parsing reagents for {extraction_kit}")
        parser = ReagentParser(xl=self.xl, submission_type=self.submission_type,
                               extraction_kit=extraction_kit)
        self.sub['reagents'] = parser.parse_reagents()

    def parse_samples(self):
        """
        Calls sample parser to pull info from the excel sheet
        """
        parser = SampleParser(xl=self.xl, submission_type=self.submission_type)
        self.sub['samples'] = parser.reconcile_samples()

    def parse_equipment(self):
        """
        Calls equipment parser to pull info from the excel sheet
        """
        parser = EquipmentParser(xl=self.xl, submission_type=self.submission_type)
        self.sub['equipment'] = parser.parse_equipment()

    def parse_tips(self):
        """
        Calls tips parser to pull info from the excel sheet
        """
        parser = TipParser(xl=self.xl, submission_type=self.submission_type)
        self.sub['tips'] = parser.parse_tips()

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

    def to_pydantic(self) -> PydSubmission:
        """
        Generates a pydantic model of scraped data for validation

        Returns:
            PydSubmission: output pydantic model
        """
        # logger.debug(f"Submission dictionary coming into 'to_pydantic':\n{pformat(self.sub)}")
        pyd_dict = copy(self.sub)
        pyd_dict['samples'] = [PydSample(**sample) for sample in self.sub['samples']]
        # logger.debug(f"Reagents: {pformat(self.sub['reagents'])}")
        pyd_dict['reagents'] = [PydReagent(**reagent) for reagent in self.sub['reagents']]
        # logger.debug(f"Equipment: {self.sub['equipment']}")
        try:
            check = bool(self.sub['equipment'])
        except TypeError:
            check = False
        if check:
            pyd_dict['equipment'] = [PydEquipment(**equipment) for equipment in self.sub['equipment']]
        else:
            pyd_dict['equipment'] = None
        try:
            check = bool(self.sub['tips'])
        except TypeError:
            check = False
        if check:
            pyd_dict['tips'] = [PydTips(**tips) for tips in self.sub['tips']]
        else:
            pyd_dict['tips'] = None
        psm = PydSubmission(filepath=self.filepath, run_custom=True, **pyd_dict)
        return psm


class InfoParser(object):
    """
    Object to parse generic info from excel sheet.
    """

    def __init__(self, xl: Workbook, submission_type: str | SubmissionType, sub_object: BasicSubmission | None = None):
        """
        Args:
            xl (Workbook): Openpyxl workbook from submitted excel file.
            submission_type (str | SubmissionType): Type of submission expected (Wastewater, Bacterial Culture, etc.)
            sub_object (BasicSubmission | None, optional): Submission object holding methods. Defaults to None.
        """
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

        Returns:
            dict: Location map of all info for this submission type
        """
        self.submission_type = dict(value=self.submission_type_obj.name, missing=True)
        # logger.debug(f"Looking up submission type: {self.submission_type['value']}")
        info_map = self.sub_object.construct_info_map(submission_type=self.submission_type_obj, mode="read")
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
                if k == "custom":
                    continue
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
            # logger.debug(f"relevant map for {sheet}: {pformat(relevant)}")
            # NOTE: make sure relevant is not an empty list.
            if not relevant:
                continue
            for item in relevant:
                # NOTE: Get cell contents at this location
                value = ws.cell(row=item['row'], column=item['column']).value
                # logger.debug(f"Value for {item['name']} = {value}")
                match item['name']:
                    case "submission_type":
                        value, missing = is_missing(value)
                        value = value.title()
                    # NOTE: is field a JSON?
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
        # NOTE: Return after running the parser components held in submission object.
        return self.sub_object.custom_info_parser(input_dict=dicto, xl=self.xl, custom_fields=self.map['custom'])


class ReagentParser(object):
    """
    Object to pull reagents from excel sheet.
    """

    def __init__(self, xl: Workbook, submission_type: str | SubmissionType, extraction_kit: str,
                 sub_object: BasicSubmission | None = None):
        """
        Args:
            xl (Workbook): Openpyxl workbook from submitted excel file.
            submission_type (str|SubmissionType): Type of submission expected (Wastewater, Bacterial Culture, etc.)
            extraction_kit (str): Extraction kit used.
            sub_object (BasicSubmission | None, optional): Submission object holding methods. Defaults to None.
        """
        # logger.debug("\n\nHello from ReagentParser!\n\n")
        if isinstance(submission_type, str):
            submission_type = SubmissionType.query(name=submission_type)
        self.submission_type_obj = submission_type
        self.sub_object = sub_object
        if isinstance(extraction_kit, dict):
            extraction_kit = extraction_kit['value']
        self.kit_object = KitType.query(name=extraction_kit)
        self.map = self.fetch_kit_info_map(submission_type=submission_type)
        # logger.debug(f"Reagent Parser map: {self.map}")
        self.xl = xl

    def fetch_kit_info_map(self, submission_type: str) -> dict:
        """
        Gets location of kit reagents from database

        Args:
            submission_type (str): Name of submission type.

        Returns:
            dict: locations of reagent info for the kit.
        """

        if isinstance(submission_type, dict):
            submission_type = submission_type['value']
        reagent_map = {k: v for k, v in self.kit_object.construct_xl_map_for_use(submission_type)}
        try:
            del reagent_map['info']
        except KeyError:
            pass
        return reagent_map

    def parse_reagents(self) -> Generator[dict, None, None]:
        """
        Extracts reagent information from the Excel form.

        Returns:
            List[PydReagent]: List of parsed reagents.
        """
        # listo = []
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
                    yield dict(role=item.strip(), lot=None, expiry=None, name=None, comment="", missing=True)
                    # continue
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
                    yield dict(role=item.strip(), lot=lot, expiry=expiry, name=name, comment=comment,
                               missing=missing)
        # return listo


class SampleParser(object):
    """
    Object to pull data for samples in excel sheet and construct individual sample objects
    """

    def __init__(self, xl: Workbook, submission_type: SubmissionType, sample_map: dict | None = None,
                 sub_object: BasicSubmission | None = None) -> None:
        """
        Args:
            xl (Workbook): Openpyxl workbook from submitted excel file.
            submission_type (SubmissionType): Type of submission expected (Wastewater, Bacterial Culture, etc.)
            sample_map (dict | None, optional): Locations in database where samples are found. Defaults to None.
            sub_object (BasicSubmission | None, optional): Submission object holding methods. Defaults to None.
        """
        # logger.debug("\n\nHello from SampleParser!\n\n")
        self.samples = []
        self.xl = xl
        if isinstance(submission_type, str):
            submission_type = SubmissionType.query(name=submission_type)
        logger.debug(f"Sample parser is using submission type: {submission_type}")
        self.submission_type = submission_type.name
        self.submission_type_obj = submission_type
        if sub_object is None:
            logger.warning(
                f"Sample parser attempting to fetch submission class with polymorphic identity: {self.submission_type}")
            sub_object = BasicSubmission.find_polymorphic_subclass(polymorphic_identity=self.submission_type)
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
        self.sample_type = self.sub_object.get_default_info("sample_type", submission_type=submission_type)
        self.samp_object = BasicSample.find_polymorphic_subclass(polymorphic_identity=self.sample_type)
        # logger.debug(f"Got sample class: {self.samp_object.__name__}")
        # logger.debug(f"info_map: {pformat(se)}")
        if sample_map is None:
            sample_info_map = self.sub_object.construct_sample_map(submission_type=self.submission_type_obj)
        else:
            sample_info_map = sample_map
        return sample_info_map

    def parse_plate_map(self) -> List[dict]:
        """
        Parse sample location/name from plate map

        Returns:
            List[dict]: List of sample ids and locations.
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

        Returns:
            List[dict]: List of basic sample info.
        """

        lmap = self.sample_info_map['lookup_table']
        ws = self.xl[lmap['sheet']]
        lookup_samples = []
        for ii, row in enumerate(range(lmap['start_row'], lmap['end_row'] + 1), start=1):
            row_dict = {k: ws.cell(row=row, column=v).value for k, v in lmap['sample_columns'].items()}
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

    def reconcile_samples(self) -> Generator[dict, None, None]:
        """
        Merges sample info from lookup table and plate map.

        Returns:
            List[dict]: Reconciled samples
        """
        if self.plate_map_samples is None or self.lookup_samples is None:
            self.samples = self.lookup_samples or self.plate_map_samples
            return
        merge_on_id = self.sample_info_map['lookup_table']['merge_on_id']
        plate_map_samples = sorted(copy(self.plate_map_samples), key=lambda d: d['id'])
        lookup_samples = sorted(copy(self.lookup_samples), key=lambda d: d[merge_on_id])
        print(pformat(plate_map_samples))
        print(pformat(lookup_samples))
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
            if not check_key_or_attr(key='submitter_id', interest=new, check_none=True):
                new['submitter_id'] = psample['id']
            new = self.sub_object.parse_samples(new)
            del new['id']
            yield new
            # samples.append(new)
        # samples = remove_key_from_list_of_dicts(samples, "id")
        # return sorted(samples, key=lambda k: (k['row'], k['column']))


class EquipmentParser(object):
    """
    Object to pull data for equipment in excel sheet
    """

    def __init__(self, xl: Workbook, submission_type: str | SubmissionType) -> None:
        """
        Args:
            xl (Workbook): Openpyxl workbook from submitted excel file.
            submission_type (str | SubmissionType): Type of submission expected (Wastewater, Bacterial Culture, etc.)
        """
        if isinstance(submission_type, str):
            submission_type = SubmissionType.query(name=submission_type)
        self.submission_type = submission_type
        self.xl = xl
        self.map = self.fetch_equipment_map()

    def fetch_equipment_map(self) -> dict:
        """
        Gets the map of equipment locations in the submission type's spreadsheet

        Returns:
            List[dict]: List of locations
        """
        return {k: v for k, v in self.submission_type.construct_equipment_map()}

    def get_asset_number(self, input: str) -> str:
        """
        Pulls asset number from string.

        Args:
            input (str): String to be scraped

        Returns:
            str: asset number
        """
        regex = Equipment.get_regex()
        # logger.debug(f"Using equipment regex: {regex} on {input}")
        try:
            return regex.search(input).group().strip("-")
        except AttributeError as e:
            logger.error(f"Error getting asset number for {input}: {e}")
            return input

    def parse_equipment(self) -> List[dict]:
        """
        Scrapes equipment from xl sheet

        Returns:
            List[dict]: list of equipment
        """
        # logger.debug(f"Equipment parser going into parsing: {pformat(self.__dict__)}")
        output = []
        # logger.debug(f"Sheets: {sheets}")
        for sheet in self.xl.sheetnames:
            ws = self.xl[sheet]
            try:
                relevant = {k: v for k, v in self.map.items() if v['sheet'] == sheet}
            except (TypeError, KeyError) as e:
                logger.error(f"Error creating relevant equipment list: {e}")
                continue
            # logger.debug(f"Relevant equipment: {pformat(relevant)}")
            previous_asset = ""
            for k, v in relevant.items():
                # logger.debug(f"Checking: {v}")
                asset = ws.cell(v['name']['row'], v['name']['column']).value
                if not check_not_nan(asset):
                    asset = previous_asset
                else:
                    previous_asset = asset
                asset = self.get_asset_number(input=asset)
                # logger.debug(f"asset: {asset}")
                eq = Equipment.query(asset_number=asset)
                if eq is None:
                    eq = Equipment.query(name=asset)
                process = ws.cell(row=v['process']['row'], column=v['process']['column']).value
                try:
                    # output.append(
                    yield dict(name=eq.name, processes=[process], role=k, asset_number=eq.asset_number,
                               nickname=eq.nickname)
                except AttributeError:
                    logger.error(f"Unable to add {eq} to list.")
                # logger.debug(f"Here is the output so far: {pformat(output)}")
        # return output


class TipParser(object):
    """
    Object to pull data for tips in excel sheet
    """

    def __init__(self, xl: Workbook, submission_type: str | SubmissionType) -> None:
        """
        Args:
            xl (Workbook): Openpyxl workbook from submitted excel file.
            submission_type (str | SubmissionType): Type of submission expected (Wastewater, Bacterial Culture, etc.)
        """
        if isinstance(submission_type, str):
            submission_type = SubmissionType.query(name=submission_type)
        self.submission_type = submission_type
        self.xl = xl
        self.map = self.fetch_tip_map()

    def fetch_tip_map(self) -> dict:
        """
        Gets the map of equipment locations in the submission type's spreadsheet

        Returns:
            List[dict]: List of locations
        """
        return {k: v for k, v in self.submission_type.construct_tips_map()}

    def parse_tips(self) -> List[dict]:
        """
        Scrapes equipment from xl sheet

        Returns:
            List[dict]: list of equipment
        """
        # logger.debug(f"Equipment parser going into parsing: {pformat(self.__dict__)}")
        output = []
        # logger.debug(f"Sheets: {sheets}")
        for sheet in self.xl.sheetnames:
            ws = self.xl[sheet]
            try:
                relevant = {k: v for k, v in self.map.items() if v['sheet'] == sheet}
            except (TypeError, KeyError) as e:
                logger.error(f"Error creating relevant equipment list: {e}")
                continue
            # logger.debug(f"Relevant equipment: {pformat(relevant)}")
            previous_asset = ""
            for k, v in relevant.items():
                asset = ws.cell(v['name']['row'], v['name']['column']).value
                if "lot" in v.keys():
                    lot = ws.cell(v['lot']['row'], v['lot']['column']).value
                else:
                    lot = None
                if not check_not_nan(asset):
                    asset = previous_asset
                else:
                    previous_asset = asset
                # logger.debug(f"asset: {asset}")
                eq = Tips.query(lot=lot, name=asset, limit=1)
                try:
                    # output.append(
                    yield dict(name=eq.name, role=k, lot=lot)
                except AttributeError:
                    logger.error(f"Unable to add {eq} to PydTips list.")
                # logger.debug(f"Here is the output so far: {pformat(output)}")
        # return output


class PCRParser(object):
    """Object to pull data from Design and Analysis PCR export file."""

    def __init__(self, filepath: Path | None = None, submission: BasicSubmission | None = None) -> None:
        """
         Args:
             filepath (Path | None, optional): file to parse. Defaults to None.
         """
        # logger.debug(f'Parsing {filepath.__str__()}')
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
                logger.error(f"Couldn't get permissions for {filepath.__str__()}. Operation might have been cancelled.")
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
        pcr = {}
        for row in iter_rows:
            try:
                key = row[0].value.lower().replace(' ', '_')
            except AttributeError as e:
                logger.error(f"No key: {row[0].value} due to {e}")
                continue
            value = row[1].value or ""
            pcr[key] = value
        pcr['imported_by'] = getuser()
        # logger.debug(f"PCR: {pformat(pcr)}")
        return pcr
