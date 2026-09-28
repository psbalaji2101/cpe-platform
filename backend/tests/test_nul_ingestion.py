import hashlib
import io
import zipfile
from sqlalchemy import select
from cpe.db import DB, Event, File, Upload
from cpe.storage import artifact_path
from cpe.ingestion import ingest
from test_platform import create, put_upload
import pytest


def test_nul_bytes_are_visible_without_changing_raw_evidence(client):
    raw = b'2026-09-25T10:00:00Z ERROR before\x00after\nINFO password=secret\x00suffix\n\xff\x00end\n'
    archive = io.BytesIO()
    with zipfile.ZipFile(archive, 'w') as z:
        z.writestr('mixed.log', raw)
        z.writestr('normal.log', b'INFO normal\n')
    case = create(client)
    upload = put_upload(client, case, archive.getvalue())
    with DB() as db:
        assert db.get(Upload, upload).status == 'Ready'
        file = db.scalar(select(File).where(File.upload_id == upload, File.path == 'mixed.log'))
        assert artifact_path('raw', file.id).read_bytes() == raw
        assert file.sha256 == hashlib.sha256(raw).hexdigest()
        assert file.metadata_json['nul_bytes_rendered'] == 3
        events = list(db.scalars(select(Event).where(Event.file_id == file.id).order_by(Event.line)))
        assert len(events) == 3
        assert 'before␀after' in events[0].message
        assert all('\x00' not in e.message for e in events)
        assert 'secret' not in events[1].message
        assert events[1].byte_start == raw.index(b'INFO')
        assert events[-1].byte_end == len(raw)
    assert client.get(f'/api/cases/{case}/search', params={'q':'before␀after'}).json()['items']


def test_unexpected_failure_has_no_sql_in_ui_and_retry_clears_error(client, monkeypatch):
    case = create(client)
    upload = put_upload(client, case, b'INFO test\n', name='test.log')
    def fail(*args):
        raise RuntimeError('INSERT INTO events private-database-detail')
    with monkeypatch.context() as m:
        m.setattr('cpe.ingestion.members', fail)
        with pytest.raises(RuntimeError):
            ingest(upload)
    with DB() as db:
        rejected = db.get(Upload, upload)
        assert rejected.status == 'Rejected'
        assert 'INSERT' not in rejected.error
        assert 'private-database-detail' not in rejected.error
    ingest(upload)
    with DB() as db:
        assert db.get(Upload, upload).status == 'Ready'
        assert db.get(Upload, upload).error == ''


def test_relative_colon_filename_is_safe_and_keeps_display_name(client):
    raw = io.BytesIO()
    name = "logs/component-2026-09-27T12:30:00.log"
    with zipfile.ZipFile(raw, 'w') as archive:
        archive.writestr(name, 'ERROR example\n')
    case = create(client)
    upload = put_upload(client, case, raw.getvalue())
    with DB() as db:
        assert db.get(Upload, upload).status == 'Ready'
        f = db.scalar(select(File).where(File.upload_id == upload))
        assert f.path == name
        assert artifact_path('raw', f.id).name == f.id


@pytest.mark.parametrize('name', ['C:relative.log', 'C:/absolute.log', '../escape.log', '/absolute.log', 'a/../../b', 'a\\b', 'a\x00b'])
def test_unsafe_paths_remain_rejected(name):
    from cpe.storage import safe_member
    with pytest.raises(ValueError):
        safe_member(name)
