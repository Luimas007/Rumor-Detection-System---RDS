import sys
from pathlib import Path
from loguru import logger

_configured = False


def setup_logger(level: str = "DEBUG", log_file: str = "logs/rds.log",
                 rotation: str = "10 MB", retention: str = "7 days") -> None:
    global _configured
    if _configured:
        return

    logger.remove()

    logger.add(
        sys.stderr,
        level=level,
        format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | "
               "<cyan>{name}</cyan>:<cyan>{line}</cyan> - <level>{message}</level>",
        colorize=True,
    )

    log_path = Path(log_file)
    log_path.parent.mkdir(parents=True, exist_ok=True)
    logger.add(
        str(log_path),
        level=level,
        rotation=rotation,
        retention=retention,
        format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {name}:{line} - {message}",
        encoding="utf-8",
    )

    _configured = True
    logger.info("Logger initialised — level={}", level)


def get_logger(name: str):
    return logger.bind(name=name)
