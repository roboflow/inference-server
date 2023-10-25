import datetime
from apscheduler.schedulers.background import BackgroundScheduler
from fastapi import FastAPI

from inference.core.env import METRICS_INTERVAL
from inference.core.version import __version__
from inference.enterprise.device_manager.container_service import (
    check_for_duplicate_aliases,
)
from inference.enterprise.device_manager.metrics_service import (
    send_metrics,
    send_latest_inferences,
)

app = FastAPI(
    title="Roboflow Device Manager",
    description="The device manager enables remote control and monitoring of Roboflow inference server containers",
    version=__version__,
    terms_of_service="https://roboflow.com/terms",
    contact={
        "name": "Roboflow Inc.",
        "url": "https://roboflow.com/contact",
        "email": "help@roboflow.com",
    },
    license_info={
        "name": "Apache 2.0",
        "url": "https://www.apache.org/licenses/LICENSE-2.0.html",
    },
    root_path="/",
)


@app.get("/")
def root():
    return {
        "name": "Roboflow Device Manager",
        "version": __version__,
        "terms_of_service": "https://roboflow.com/terms",
        "contact": {
            "name": "Roboflow Inc.",
            "url": "https://roboflow.com/contact",
            "email": "help@roboflow.com",
        },
        "license_info": {
            "name": "Apache 2.0",
            "url": "https://www.apache.org/licenses/LICENSE-2.0.html",
        },
    }


check_for_duplicate_aliases()

scheduler = BackgroundScheduler(job_defaults={"coalesce": True, "max_instances": 3})
scheduler.add_job(
    send_metrics,
    "interval",
    seconds=METRICS_INTERVAL,
    next_run_time=datetime.datetime.now(),
)
scheduler.add_job(send_latest_inferences, "interval", seconds=5)
scheduler.start()
