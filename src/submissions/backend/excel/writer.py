import logging
from copy import copy
from pathlib import Path
from typing import List

from openpyxl import load_workbook, Workbook
from tools import row_keys
from backend.db.models import SubmissionType, KitType
from backend.validators.pydant import PydSubmission
from io import BytesIO
from collections import OrderedDict

logger = logging.getLogger(f"submissions.{__name__}")


class SheetWriter(object):
    """
    object to pull and contain data from excel file
    """

    def __init__(self, submission: PydSubmission, missing_only: bool = False):
        """
        Args:
            filepath (Path | None, optional): file path to excel sheet. Defaults to None.
        """
        self.sub = OrderedDict(submission.improved_dict())
        for k, v in self.sub.items():
            match k:
                case 'filepath':
                    self.__setattr__(k, v)
                case 'submission_type':
                    # self.__setattr__('submission_type', submission.submission_type['value'])
                    self.sub[k] = v['value']
                    self.submission_type = SubmissionType.query(name=v['value'])
                case _:
                    if isinstance(v, dict):
                        self.sub[k] = v['value']
                    else:
                        self.sub[k] = v
        logger.debug(f"\n\nWriting to {submission.filepath.__str__()}\n\n")

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
        self.workbook = workbook
        self.write_info()
        self.write_reagents()
        self.write_samples()
        self.write_equipment()

    def write_info(self):
        disallowed = ['filepath', 'reagents', 'samples', 'equipment', 'controls']
        info_dict = {k: v for k, v in self.sub.items() if k not in disallowed}
        writer = InfoWriter(xl=self.workbook, submission_type=self.submission_type, info_dict=info_dict)
        self.xl = writer.write_info()

    def write_reagents(self):
        reagent_list = self.sub['reagents']
        writer = ReagentWriter(xl=self.workbook, submission_type=self.submission_type,
                               extraction_kit=self.sub['extraction_kit'], reagent_list=reagent_list)
        self.xl = writer.write_reagents()

    def write_samples(self):
        sample_list = self.sub['samples']
        writer = SampleWriter(xl=self.workbook, submission_type=self.submission_type, sample_list=sample_list)
        self.xl = writer.write_samples()

    def write_equipment(self):
        equipment_list = self.sub['equipment']
        writer = EquipmentWriter(xl=self.workbook, submission_type=self.submission_type, equipment_list=equipment_list)
        self.xl = writer.write_equipment()


class InfoWriter(object):

    def __init__(self, xl: Workbook, submission_type: SubmissionType | str, info_dict: dict):
        if isinstance(submission_type, str):
            submission_type = SubmissionType.query(name=submission_type)
        self.submission_type = submission_type
        self.xl = xl
        map = submission_type.construct_info_map(mode='write')
        self.info = self.reconcile_map(info_dict, map)

    def reconcile_map(self, info_dict: dict, map: dict) -> dict:
        output = {}
        for k, v in info_dict.items():
            if v is None:
                continue
            dicto = {}
            try:
                dicto['locations'] = map[k]
            except KeyError:
                continue
            dicto['value'] = v
            if len(dicto) > 0:
                output[k] = dicto
        return output

    def write_info(self):
        for k, v in self.info.items():
            try:
                locations = v['locations']
            except KeyError:
                logger.error(f"No locations for {k}, skipping")
                continue
            for loc in locations:
                logger.debug(f"Writing {k} to {loc['sheet']}, row: {loc['row']}, column: {loc['column']}")
                sheet = self.xl[loc['sheet']]
                sheet.cell(row=loc['row'], column=loc['column'], value=v['value'])
        return self.xl


class ReagentWriter(object):

    def __init__(self, xl: Workbook, submission_type: SubmissionType | str, extraction_kit: KitType | str,
                 reagent_list: list):
        self.xl = xl
        if isinstance(submission_type, str):
            submission_type = SubmissionType.query(name=submission_type)
        if isinstance(extraction_kit, str):
            kit_type = KitType.query(name=extraction_kit)
        map = kit_type.construct_xl_map_for_use(submission_type)
        self.reagents = self.reconcile_map(reagent_list=reagent_list, map=map)

    def reconcile_map(self, reagent_list, map) -> List[dict]:
        output = []
        for reagent in reagent_list:
            try:
                mp_info = map[reagent['type']]
            except KeyError:
                continue
            placeholder = copy(reagent)
            for k, v in reagent.items():
                try:
                    dicto = dict(value=v, row=mp_info[k]['row'], column=mp_info[k]['column'])
                except KeyError as e:
                    logger.error(f"Keyerror: {e}")
                    dicto = v
                placeholder[k] = dicto
                placeholder['sheet'] = mp_info['sheet']
            output.append(placeholder)
        return output

    def write_reagents(self):
        for reagent in self.reagents:
            sheet = self.xl[reagent['sheet']]
            for k, v in reagent.items():
                if not isinstance(v, dict):
                    continue
                logger.debug(
                    f"Writing {reagent['type']} {k} to {reagent['sheet']}, row: {v['row']}, column: {v['column']}")
                sheet.cell(row=v['row'], column=v['column'], value=v['value'])
        return self.xl


class SampleWriter(object):

    def __init__(self, xl: Workbook, submission_type: SubmissionType | str, sample_list: list):
        if isinstance(submission_type, str):
            submission_type = SubmissionType.query(name=submission_type)
        self.submission_type = submission_type
        self.xl = xl
        self.map = submission_type.construct_sample_map()['lookup_table']
        self.samples = self.reconcile_map(sample_list)

    def reconcile_map(self, sample_list: list):
        output = []
        multiples = ['row', 'column', 'assoc_id', 'submission_rank']
        for sample in sample_list:
            for assoc in zip(sample['row'], sample['column'], sample['submission_rank']):
                new = dict(row=assoc[0], column=assoc[1], submission_rank=assoc[2])
                for k, v in sample.items():
                    if k in multiples:
                        continue
                    new[k] = v
                output.append(new)
        return sorted(output, key=lambda k: k['submission_rank'])

    def write_samples(self):
        sheet = self.xl[self.map['sheet']]
        columns = self.map['sample_columns']
        # rows = range(self.map['start_row'], self.map['end_row']+1)
        for ii, sample in enumerate(self.samples):
            row = self.map['start_row'] + (sample['submission_rank'] - 1)
            for k, v in sample.items():
                try:
                    column = columns[k]
                except KeyError:
                    continue
                sheet.cell(row=row, column=column, value=v)
        return self.xl


class EquipmentWriter(object):

    def __init__(self, xl: Workbook, submission_type: SubmissionType | str, equipment_list: list):
        if isinstance(submission_type, str):
            submission_type = SubmissionType.query(name=submission_type)
        self.submission_type = submission_type
        self.xl = xl
        map = self.submission_type.construct_equipment_map()
        self.equipment = self.reconcile_map(equipment_list=equipment_list, map=map)

    def reconcile_map(self, equipment_list: list, map: list):
        output = []
        for ii, equipment in enumerate(equipment_list, start=1):
            mp_info = map[equipment['role']]
            placeholder = copy(equipment)
            for jj, (k, v) in enumerate(equipment.items(), start=1):
                try:
                    dicto = dict(value=v, row=mp_info[k]['row'], column=mp_info[k]['column'])
                except KeyError as e:
                    logger.error(f"Keyerror: {e}")
                    dicto = dict(value=v, row=ii, column=jj)
                placeholder[k] = dicto
                try:
                    placeholder['sheet'] = mp_info['sheet']
                except KeyError:
                    placeholder['sheet'] = "Equipment"
            output.append(placeholder)
        return output

    def write_equipment(self):
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
                logger.debug(
                    f"Writing {equipment['role']} {k} to {equipment['sheet']}, row: {v['row']}, column: {v['column']}")
                if isinstance(v['value'], list):
                    v['value'] = v['value'][0]
                sheet.cell(row=v['row'], column=v['column'], value=v['value'])
        return self.xl
