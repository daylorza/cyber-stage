import db


def test_delete_listing_and_block_active_jobs(client):
    with db.connect() as conn:
        db.insert_listing(conn, {"id": "lst_delete", "status": "draft", "source": "upload"})
        db.insert_job(conn, "job_delete", "lst_delete", "listing")
    assert client.delete('/api/listings/lst_delete').status_code == 409
    db.update_job('job_delete', status='done')
    assert client.delete('/api/listings/lst_delete').status_code == 200
    assert client.get('/api/listings/lst_delete').status_code == 404
    assert db.get_job('job_delete') is None
    assert client.delete('/api/listings/lst_delete').status_code == 404
