"""
contains writer objects for pushing values to submission sheet templates.
"""
import logging
from copy import copy
from operator import itemgetter
from pathlib import Path
# from pathlib import Path
from pprint import pformat
from typing import List, Generator
from openpyxl import load_workbook, Workbook
from backend.db.models import SubmissionType, KitType, BasicSubmission
from backend.validators.pydant import PydSubmission
from io import BytesIO
from collections import OrderedDict
from tools import jinja_template_loading
from docxtpl import DocxTemplate
from docx import Document

logger = logging.getLogger(f"submissions.{__name__}")


class SheetWriter(object):
    """
    object to manage data placement into excel file
    """

    def __init__(self, submission: PydSubmission, missing_only: bool = False):
        """
        Args:
            submission (PydSubmission): Object containing submission information.
            missing_only (bool, optional): Whether to only fill in missing values. Defaults to False.
        """
        self.sub = OrderedDict(submission.improved_dict())
        for k, v in self.sub.items():
            match k:
                case 'filepath':
                    self.__setattr__(k, v)
                case 'submission_type':
                    self.sub[k] = v['value']
                    self.submission_type = SubmissionType.query(name=v['value'])
                    self.sub_object = BasicSubmission.find_polymorphic_subclass(
                        polymorphic_identity=self.submission_type)
                case _:
                    if isinstance(v, dict):
                        self.sub[k] = v['value']
                    else:
                        self.sub[k] = v
        # logger.debug(f"\n\nWriting to {submission.filepath.__str__()}\n\n")
        if self.filepath.stem.startswith("tmp"):
            template = self.submission_type.template_file
            workbook = load_workbook(BytesIO(template))
            missing_only = False
        else:
            try:
                workbook = load_workbook(self.filepath)
            except Exception as e:
                logger.error(f"Couldn't open workbook due to {e}")
                template = self.submission_type.template_file
                workbook = load_workbook(BytesIO(template))
                missing_only = False
        # self.workbook = workbook
        self.xl = workbook
        self.write_info()
        self.write_reagents()
        self.write_samples()
        self.write_equipment()
        self.write_tips()

    def write_info(self):
        """
        Calls info writer
        """
        disallowed = ['filepath', 'reagents', 'samples', 'equipment', 'controls']
        info_dict = {k: v for k, v in self.sub.items() if k not in disallowed}
        writer = InfoWriter(xl=self.xl, submission_type=self.submission_type, info_dict=info_dict)
        self.xl = writer.write_info()

    def write_reagents(self):
        """
        Calls reagent writer
        """
        reagent_list = self.sub['reagents']
        writer = ReagentWriter(xl=self.xl, submission_type=self.submission_type,
                               extraction_kit=self.sub['extraction_kit'], reagent_list=reagent_list)
        self.xl = writer.write_reagents()

    def write_samples(self):
        """
        Calls sample writer
        """
        sample_list = self.sub['samples']
        writer = SampleWriter(xl=self.xl, submission_type=self.submission_type, sample_list=sample_list)
        self.xl = writer.write_samples()

    def write_equipment(self):
        """
        Calls equipment writer
        """
        equipment_list = self.sub['equipment']
        writer = EquipmentWriter(xl=self.xl, submission_type=self.submission_type, equipment_list=equipment_list)
        self.xl = writer.write_equipment()

    def write_tips(self):
        """
        Calls tip writer
        """
        tips_list = self.sub['tips']
        writer = TipWriter(xl=self.xl, submission_type=self.submission_type, tips_list=tips_list)
        self.xl = writer.write_tips()


class InfoWriter(object):
    """
    object to write general submission info into excel file
    """

    def __init__(self, xl: Workbook, submission_type: SubmissionType | str, info_dict: dict,
                 sub_object: BasicSubmission | None = None):
        """
        Args:
            xl (Workbook): Openpyxl workbook from submitted excel file.
            submission_type (SubmissionType | str): Type of submission expected (Wastewater, Bacterial Culture, etc.)
            info_dict (dict): Dictionary of information to write.
            sub_object (BasicSubmission | None, optional): Submission object containing methods. Defaults to None.
        """
        logger.debug(f"Info_dict coming into InfoWriter: {pformat(info_dict)}")
        if isinstance(submission_type, str):
            submission_type = SubmissionType.query(name=submission_type)
        if sub_object is None:
            sub_object = BasicSubmission.find_polymorphic_subclass(polymorphic_identity=submission_type.name)
        self.submission_type = submission_type
        self.sub_object = sub_object
        self.xl = xl
        self.info_map = submission_type.construct_info_map(mode='write')
        self.info = self.reconcile_map(info_dict, self.info_map)
        # logger.debug(pformat(self.info))

    def reconcile_map(self, info_dict: dict, info_map: dict) -> dict:
        """
        Merge info with its locations

        Args:
            info_dict (dict): dictionary of info items
            info_map (dict): dictionary of info locations

        Returns:
            dict: merged dictionary
        """
        # output = {}
        for k, v in info_dict.items():
            if v is None:
                continue
            if k == "custom":
                continue
            dicto = {}
            try:
                dicto['locations'] = info_map[k]
            except KeyError:
                # continue
                pass
            dicto['value'] = v
            if len(dicto) > 0:
                # output[k] = dicto
                yield k, dicto
        # logger.debug(f"Reconciled info: {pformat(output)}")
        # return output

    def write_info(self) -> Workbook:
        """
        Performs write operations

        Returns:
            Workbook: workbook with info written.
        """
        for k, v in self.info:
            # NOTE: merge all comments to fit in single cell.
            if k == "comment" and isinstance(v['value'], list):
                json_join = [item['text'] for item in v['value'] if 'text' in item.keys()]
                v['value'] = "\n".join(json_join)
            try:
                locations = v['locations']
            except KeyError:
                logger.error(f"No locations for {k}, skipping")
                continue
            for loc in locations:
                logger.debug(f"Writing {k} to {loc['sheet']}, row: {loc['row']}, column: {loc['column']}")
                sheet = self.xl[loc['sheet']]
                sheet.cell(row=loc['row'], column=loc['column'], value=v['value'])
        return self.sub_object.custom_info_writer(self.xl, info=self.info, custom_fields=self.info_map['custom'])


class ReagentWriter(object):
    """
    object to write reagent data into excel file
    """

    def __init__(self, xl: Workbook, submission_type: SubmissionType | str, extraction_kit: KitType | str,
                 reagent_list: list):
        """
        Args:
            xl (Workbook): Openpyxl workbook from submitted excel file.
            submission_type (SubmissionType | str): Type of submission expected (Wastewater, Bacterial Culture, etc.)
            extraction_kit (KitType | str): Extraction kit used.
            reagent_list (list): List of reagent dicts to be written to excel.
        """
        self.xl = xl
        if isinstance(submission_type, str):
            submission_type = SubmissionType.query(name=submission_type)
        if isinstance(extraction_kit, str):
            kit_type = KitType.query(name=extraction_kit)
        reagent_map = {k: v for k, v in kit_type.construct_xl_map_for_use(submission_type)}
        # self.reagents = {k: v for k, v in self.reconcile_map(reagent_list=reagent_list, reagent_map=reagent_map)}
        self.reagents = self.reconcile_map(reagent_list=reagent_list, reagent_map=reagent_map)

    def reconcile_map(self, reagent_list: List[dict], reagent_map: dict) -> Generator[dict, None, None]:
        """
        Merge reagents with their locations

        Args:
            reagent_list (List[dict]): List of reagent dictionaries
            reagent_map (dict): Reagent locations

        Returns:
            List[dict]: merged dictionary
        """
        # output = []
        for reagent in reagent_list:
            try:
                mp_info = reagent_map[reagent['role']]
            except KeyError:
                continue
            placeholder = copy(reagent)
            for k, v in reagent.items():
                try:
                    dicto = dict(value=v, row=mp_info[k]['row'], column=mp_info[k]['column'])
                except KeyError as e:
                    logger.error(f"KeyError: {e}")
                    dicto = v
                placeholder[k] = dicto
                placeholder['sheet'] = mp_info['sheet']
            # output.append(placeholder)
            yield placeholder
        # return output

    def write_reagents(self) -> Workbook:
        """
        Performs write operations

        Returns:
            Workbook: Workbook with reagents written
        """
        for reagent in self.reagents:
            sheet = self.xl[reagent['sheet']]
            for k, v in reagent.items():
                if not isinstance(v, dict):
                    continue
                # logger.debug(
                # f"Writing {reagent['type']} {k} to {reagent['sheet']}, row: {v['row']}, column: {v['column']}")
                sheet.cell(row=v['row'], column=v['column'], value=v['value'])
        return self.xl


class SampleWriter(object):
    """
    object to write sample data into excel file
    """

    def __init__(self, xl: Workbook, submission_type: SubmissionType | str, sample_list: list):
        """
        Args:
            xl (Workbook): Openpyxl workbook from submitted excel file.
            submission_type (SubmissionType | str): Type of submission expected (Wastewater, Bacterial Culture, etc.)
            sample_list (list): List of sample dictionaries to be written to excel file.
        """
        if isinstance(submission_type, str):
            submission_type = SubmissionType.query(name=submission_type)
        self.submission_type = submission_type
        self.xl = xl
        self.sample_map = submission_type.construct_sample_map()['lookup_table']
        # self.samples = self.reconcile_map(sample_list)
        samples = [item for item in self.reconcile_map(sample_list)]
        self.samples = sorted(samples, key=lambda k: k['submission_rank'])

    def reconcile_map(self, sample_list: list) -> Generator[dict, None, None]:
        """
        Merge sample info with locations

        Args:
            sample_list (list): List of sample information

        Returns:
            List[dict]: List of merged dictionaries
        """
        # output = []
        multiples = ['row', 'column', 'assoc_id', 'submission_rank']
        for sample in sample_list:
            # logger.debug(f"Writing sample: {sample}")
            for assoc in zip(sample['row'], sample['column'], sample['submission_rank']):
                new = dict(row=assoc[0], column=assoc[1], submission_rank=assoc[2])
                for k, v in sample.items():
                    if k in multiples:
                        continue
                    new[k] = v
                yield new
        # return sorted(output, key=lambda k: k['submission_rank'])

    def write_samples(self) -> Workbook:
        """
        Performs writing operations.

        Returns:
            Workbook: Workbook with samples written
        """
        sheet = self.xl[self.sample_map['sheet']]
        columns = self.sample_map['sample_columns']
        for sample in self.samples:
            row = self.sample_map['start_row'] + (sample['submission_rank'] - 1)
            for k, v in sample.items():
                try:
                    column = columns[k]
                except KeyError:
                    continue
                sheet.cell(row=row, column=column, value=v)
        return self.xl


class EquipmentWriter(object):
    """
    object to write equipment data into excel file
    """

    def __init__(self, xl: Workbook, submission_type: SubmissionType | str, equipment_list: list):
        """
        Args:
            xl (Workbook): Openpyxl workbook from submitted excel file.
            submission_type (SubmissionType | str): Type of submission expected (Wastewater, Bacterial Culture, etc.)
            equipment_list (list): List of equipment dictionaries to write to excel file.
        """
        if isinstance(submission_type, str):
            submission_type = SubmissionType.query(name=submission_type)
        self.submission_type = submission_type
        self.xl = xl
        equipment_map = {k: v for k, v in self.submission_type.construct_equipment_map()}
        self.equipment = self.reconcile_map(equipment_list=equipment_list, equipment_map=equipment_map)

    def reconcile_map(self, equipment_list: list, equipment_map: dict) -> Generator[dict, None, None]:
        """
        Merges equipment with location data

        Args:
            equipment_list (list): List of equipment
            equipment_map (dict): Dictionary of equipment locations

        Returns:
            List[dict]: List of merged dictionaries 
        """
        # output = []
        if equipment_list is None:
            return
        for ii, equipment in enumerate(equipment_list, start=1):
            mp_info = equipment_map[equipment['role']]
            # logger.debug(f"{equipment['role']} map: {mp_info}")
            placeholder = copy(equipment)
            if mp_info == {}:
                for jj, (k, v) in enumerate(equipment.items(), start=1):
                    dicto = dict(value=v, row=ii, column=jj)
                    placeholder[k] = dicto
            else:
                for jj, (k, v) in enumerate(equipment.items(), start=1):
                    try:
                        dicto = dict(value=v, row=mp_info[k]['row'], column=mp_info[k]['column'])
                    except KeyError as e:
                        # logger.error(f"Keyerror: {e}")
                        continue
                    placeholder[k] = dicto
                if "asset_number" not in mp_info.keys():
                    placeholder['name']['value'] = f"{equipment['name']} - {equipment['asset_number']}"
            try:
                placeholder['sheet'] = mp_info['sheet']
            except KeyError:
                placeholder['sheet'] = "Equipment"
            # logger.debug(f"Final output of {equipment['role']} : {placeholder}")
            yield placeholder
            # output.append(placeholder)
        # return output

    def write_equipment(self) -> Workbook:
        """
        Performs write operations

        Returns:
            Workbook: Workbook with equipment written
        """
        for equipment in self.equipment:
            try:
                sheet = self.xl[equipment['sheet']]
            except KeyError:
                self.xl.create_sheet("Equipment")
            finally:
                sheet = self.xl[equipment['sheet']]
            for k, v in equipment.items():
                if not isinstance(v, dict):
                    continue
                # logger.debug(
                #     f"Writing {k}: {v['value']} to {equipment['sheet']}, row: {v['row']}, column: {v['column']}")
                if isinstance(v['value'], list):
                    v['value'] = v['value'][0]
                try:
                    sheet.cell(row=v['row'], column=v['column'], value=v['value'])
                except AttributeError as e:
                    logger.error(f"Couldn't write to {equipment['sheet']}, row: {v['row']}, column: {v['column']}")
                    logger.error(e)
        return self.xl


class TipWriter(object):
    """
    object to write tips data into excel file
    """

    def __init__(self, xl: Workbook, submission_type: SubmissionType | str, tips_list: list):
        """
        Args:
            xl (Workbook): Openpyxl workbook from submitted excel file.
            submission_type (SubmissionType | str): Type of submission expected (Wastewater, Bacterial Culture, etc.)
            tips_list (list): List of tip dictionaries to write to the excel file.
        """
        if isinstance(submission_type, str):
            submission_type = SubmissionType.query(name=submission_type)
        self.submission_type = submission_type
        self.xl = xl
        tips_map = {k: v for k, v in self.submission_type.construct_tips_map()}
        self.tips = self.reconcile_map(tips_list=tips_list, tips_map=tips_map)

    def reconcile_map(self, tips_list: List[dict], tips_map: dict) -> Generator[dict, None, None]:
        """
        Merges tips with location data

        Args:
            tips_list (List[dict]): List of tips
            tips_map (dict): Tips locations

        Returns:
            List[dict]: List of merged dictionaries
        """
        # output = []
        if tips_list is None:
            return
        for ii, tips in enumerate(tips_list, start=1):
            mp_info = tips_map[tips['role']]
            # logger.debug(f"{tips['role']} map: {mp_info}")
            placeholder = copy(tips)
            if mp_info == {}:
                for jj, (k, v) in enumerate(tips.items(), start=1):
                    dicto = dict(value=v, row=ii, column=jj)
                    placeholder[k] = dicto
            else:
                for jj, (k, v) in enumerate(tips.items(), start=1):
                    try:
                        dicto = dict(value=v, row=mp_info[k]['row'], column=mp_info[k]['column'])
                    except KeyError as e:
                        # logger.error(f"Keyerror: {e}")
                        continue
                    placeholder[k] = dicto
            try:
                placeholder['sheet'] = mp_info['sheet']
            except KeyError:
                placeholder['sheet'] = "Tips"
            # logger.debug(f"Final output of {tips['role']} : {placeholder}")
            yield placeholder
            # output.append(placeholder)
        # return output

    def write_tips(self) -> Workbook:
        """
        Performs write operations

        Returns:
            Workbook: Workbook with tips written
        """
        for tips in self.tips:
            try:
                sheet = self.xl[tips['sheet']]
            except KeyError:
                self.xl.create_sheet("Tips")
            finally:
                sheet = self.xl[tips['sheet']]
            for k, v in tips.items():
                if not isinstance(v, dict):
                    continue
                # logger.debug(
                #     f"Writing {k}: {v['value']} to {equipment['sheet']}, row: {v['row']}, column: {v['column']}")
                if isinstance(v['value'], list):
                    v['value'] = v['value'][0]
                try:
                    sheet.cell(row=v['row'], column=v['column'], value=v['value'])
                except AttributeError as e:
                    logger.error(f"Couldn't write to {tips['sheet']}, row: {v['row']}, column: {v['column']}")
                    logger.error(e)
        return self.xl


class DocxWriter(object):
    """
    Object to render 
    """

    def __init__(self, base_dict: dict):
        """
        Args:
            base_dict (dict): dictionary of info to be written to template.
        """
        self.sub_obj = BasicSubmission.find_polymorphic_subclass(polymorphic_identity=base_dict['submission_type'])
        env = jinja_template_loading()
        temp_name = f"{base_dict['submission_type'].replace(' ', '').lower()}_subdocument.docx"
        path = Path(env.loader.__getattribute__("searchpath")[0])
        main_template = path.joinpath("basicsubmission_document.docx")
        subdocument = path.joinpath(temp_name)
        if subdocument.exists():
            main_template = self.create_merged_template(main_template, subdocument)
        self.template = DocxTemplate(main_template)
        base_dict['platemap'] = self.create_plate_map(base_dict['samples'], rows=8, columns=12)
        # logger.debug(pformat(base_dict['plate_map']))
        try:
            base_dict['excluded'] += ["platemap"]
        except KeyError:
            base_dict['excluded'] = ["platemap"]
        base_dict = self.sub_obj.custom_docx_writer(base_dict, tpl_obj=self.template)
        # logger.debug(f"Base dict: {pformat(base_dict)}")
        self.template.render({"sub": base_dict})

    @classmethod
    def create_plate_map(self, sample_list: List[dict], rows: int = 0, columns: int = 0) -> List[list]:
        sample_list = sorted(sample_list, key=itemgetter('column', 'row'))
        if rows == 0:
            rows = max([sample['row'] for sample in sample_list])
        if columns == 0:
            columns = max([sample['column'] for sample in sample_list])
        # output = []
        for row in range(0, rows):
            contents = [''] * columns
            for column in range(0, columns):
                try:
                    ooi = [item for item in sample_list if item['row'] == row + 1 and item['column'] == column + 1][0]
                except IndexError:
                    continue
                contents[column] = ooi['submitter_id']
            # contents = [sample['submitter_id'] for sample in sample_list if sample['row'] == row + 1]
            # contents = [f"{sample['row']},{sample['column']}" for sample in sample_list if sample['row'] == row + 1]
            if len(contents) < columns:
                contents += [''] * (columns - len(contents))
            if not contents:
                contents = [''] * columns
            yield contents
            # output.append(contents)
        # return output

    def create_merged_template(self, *args) -> BytesIO:
        """
        Appends submission specific information

        Returns:
            BytesIO: Merged docx template
        """
        merged_document = Document()
        output = BytesIO()
        for index, file in enumerate(args):
            sub_doc = Document(file)
            # Don't add a page break if you've reached the last file.
            # if index < len(args) - 1:
            #     sub_doc.add_page_break()
            for element in sub_doc.element.body:
                merged_document.element.body.append(element)
        merged_document.save(output)
        return output

    def save(self, filename: Path | str):
        if isinstance(filename, str):
            filename = Path(filename)
        self.template.save(filename)
