"""
script meant to copy database data to new file. Currently for Sqlite only
"""
import logging, shutil, pyodbc
from datetime import date
from pathlib import Path
from tools import Settings
from .. import register_script

logger = logging.getLogger(f"submissions.{__name__}")

@register_script
def backup_database(ctx: Settings):
    """
    Copies the database into the backup directory the first time it is opened every month.
    """
    month = date.today().strftime("%Y-%m")
    current_month_bak = Path(ctx.backup_path).joinpath(f"submissions_backup-{month}").resolve()
    logger.info(f"Here is the db directory: {ctx.database_path}")
    logger.info(f"Here is the backup directory: {ctx.backup_path}")
    match ctx.database_schema:
        case "sqlite":
            db_path = ctx.database_path.joinpath(ctx.database_name).with_suffix(".db")
            current_month_bak = current_month_bak.with_suffix(".db")
            if not current_month_bak.exists() and "Archives" not in db_path.__str__():
                logger.info("No backup found for this month, backing up database.")
                try:
                    shutil.copyfile(db_path, current_month_bak)
                except PermissionError as e:
                    logger.error(f"Couldn't backup database due to: {e}")
        case "postgresql+psycopg2":
            logger.warning(f"Backup function not yet implemented for psql")
            current_month_bak = current_month_bak.with_suffix(".psql")
        case "mssql+pyodbc":
            logger.warning(f"{ctx.database_schema} backup is currently experiencing permission issues")
            current_month_bak = current_month_bak.with_suffix(".bak")
            return
            if not current_month_bak.exists():
                logger.info(f"No backup found for this month, backing up database to {current_month_bak}.")
                connection = pyodbc.connect(driver='{ODBC Driver 18 for SQL Server}',
                                             server=f'{ctx.database_path}', database=f'{ctx.database_name}',
                                             trusted_connection='yes', trustservercertificate="yes", autocommit=True)
                backup = f"BACKUP DATABASE [{ctx.database_name}] TO DISK = N'{current_month_bak}'"
                cursor = connection.cursor().execute(backup)
                connection.close()
