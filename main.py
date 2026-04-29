from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, HttpUrl
from datetime import datetime, timezone
from PIL import Image, ExifTags
import requests
import tempfile
import hashlib
import mimetypes
import os

app = FastAPI(title="Media Metadata API")


class AnalyzeRequest(BaseModel):
    url: HttpUrl
    job_type: str
    object_type: str


def hash_file(path: str, algorithm: str):
    h = hashlib.new(algorithm)
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()


def download_file(url: str):
    response = requests.get(url, timeout=30)
    response.raise_for_status()

    content_type = response.headers.get("content-type", "").split(";")[0]
    extension = mimetypes.guess_extension(content_type) or ".jpg"

    temp = tempfile.NamedTemporaryFile(delete=False, suffix=extension)
    temp.write(response.content)
    temp.close()

    return temp.name, content_type


def extract_exif(image: Image.Image):
    exif_data = {}

    raw_exif = image.getexif()
    if not raw_exif:
        return exif_data

    for tag_id, value in raw_exif.items():
        tag = ExifTags.TAGS.get(tag_id, tag_id)
        exif_data[str(tag)] = str(value)

    return exif_data


@app.get("/")
def home():
    return {"status": "API funcionando"}


@app.post("/analyze-image")
def analyze_image(payload: AnalyzeRequest):
    if payload.object_type.lower() != "image":
        raise HTTPException(status_code=400, detail="object_type precisa ser 'image'")

    try:
        file_path, mime_type = download_file(str(payload.url))

        filename = os.path.basename(file_path)
        extension = filename.split(".")[-1].lower()
        size_bytes = os.path.getsize(file_path)

        sha256 = hash_file(file_path, "sha256")
        md5 = hash_file(file_path, "md5")

        image = Image.open(file_path)
        width, height = image.size
        exif = extract_exif(image)

        dpi = image.info.get("dpi", (None, None))

        executed_at = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

        result = [
            {
                "schema_version": "1.0",
                "job_type": payload.job_type,
                "object_type": payload.object_type,
                "extractor": {
                    "source": "python_pillow",
                    "tool": "Pillow",
                    "tool_version": Image.__version__ if hasattr(Image, "__version__") else None,
                    "executed_at": executed_at,
                    "mocked": False
                },
                "technical": {
                    "file": {
                        "filename": filename,
                        "extension": extension,
                        "mime_type": mime_type,
                        "size_bytes": size_bytes,
                        "hash_sha256": sha256,
                        "hash_md5": md5
                    },
                    "dimensions": {
                        "width": width,
                        "height": height,
                        "orientation": exif.get("Orientation"),
                        "dpi_x": dpi[0],
                        "dpi_y": dpi[1],
                        "resolution_unit": "inches"
                    },
                    "image": {
                        "color_mode": image.mode,
                        "color_space": exif.get("ColorSpace"),
                        "color_profile": image.info.get("icc_profile") is not None,
                        "bits_per_sample": None,
                        "color_components": len(image.getbands()),
                        "subsampling": None,
                        "encoding_process": None
                    },
                    "capture": {
                        "make": exif.get("Make"),
                        "camera_model": exif.get("Model"),
                        "software": exif.get("Software"),
                        "datetime_original": exif.get("DateTimeOriginal"),
                        "create_date": exif.get("DateTimeDigitized"),
                        "modify_date": exif.get("DateTime"),
                        "exposure_time": exif.get("ExposureTime"),
                        "f_number": exif.get("FNumber"),
                        "iso": exif.get("ISOSpeedRatings"),
                        "focal_length": exif.get("FocalLength"),
                        "white_balance": exif.get("WhiteBalance"),
                        "flash": exif.get("Flash")
                    },
                    "location": {
                        "gps_latitude_ref": None,
                        "gps_latitude": None,
                        "gps_longitude_ref": None,
                        "gps_longitude": None,
                        "gps_position": None
                    },
                    "storage": {
                        "engine": "public_url"
                    }
                },
                "raw": {
                    "exif": exif
                }
            }
        ]

        os.remove(file_path)
        return result

    except requests.exceptions.RequestException as e:
        raise HTTPException(status_code=400, detail=f"Erro ao baixar imagem: {str(e)}")

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erro ao analisar imagem: {str(e)}")
