import click
from datetime import datetime
import logging
from os import environ
from flask import Flask, request, abort, render_template
from cos import CloudObjectStorage, COSError


# FileHandler contains all of the file download/upload/delete logic.
# If you want to add some actual file processing, hook it in here.
class FileHandler():
    def __init__(self, cos_client, source_bucket, destination_bucket, file):
        self.cos_client = cos_client
        self.source_bucket = source_bucket
        self.destination_bucket = destination_bucket
        self.file = file

    def do(self):
        object = self.cos_client.get_file(
            bucket_name=self.source_bucket,
            file=self.file)

        logging.info('File downloaded')
        logging.info('Processing file')
        # Since the COS object has been stored as a local file, you'd
        # need to read that in and process it, then write the results back
        # out to another file (or store them in a file-like object).
        # This demo program does no actual processing of the file contents.
        logging.info('Processing complete')
        logging.info('Uploading file %s to COS bucket %s',
                     self.file, self.destination_bucket)

        self.cos_client.put_file(
            bucket_name=self.destination_bucket,
            file=self.file)

        logging.info('Upload complete')

        try:
            logging.info('Deleting file %s from bucket %s',
                         self.file, self.source_bucket)
            self.cos_client.delete_file(
                bucket_name=self.source_bucket, file=self.file)
        except COSError as e:
            logging.warning('Error when trying to delete file %s from bucket %s',
                            self.file, self.source_bucket)
            raise e


def create_server(cos_client=None, destination_bucket=None, source_bucket=None):
    event_stats = {'cron': 0, 'cron_error': 0, 'cos': 0, 'cos_error': 0}
    event_history = []
    buckets = [source_bucket, destination_bucket]

    app = Flask(__name__)

    # Retrieve a table showing each file known to us, along with its state
    # (present, not present, if present version/size/timestamp) within each
    # known bucket.  We'll use this to build the reconciliation hook for cron
    # events later.
    @app.route('/files', methods=['GET'])
    def get_files():
        file_inventory = {}
        # Check each bucket, get the ObjectSummary listing for that bucket,
        # store in nested dicts filename -> bucket -> file version info for
        # that bucket
        for b in buckets:
            bucket_files = cos_client.get_files_info(bucket_name=b)
            for f, f_info in bucket_files.items():
                if f not in file_inventory.keys():
                    file_inventory[f] = {}
                file_inventory[f][b] = f_info
        return render_template('files.html',
                               file_names=sorted(file_inventory.keys()),
                               files=file_inventory,
                               buckets=buckets)

    @app.route('/events/stats', methods=['GET'])
    def get_event_stats():
        return event_stats

    @app.route('/events/history', methods=['GET'])
    def get_event_history():
        return render_template('history.html', events=event_history)

    @app.route('/events/cos', methods=['POST'])
    def handle_cos_event():
        event_timestamp = datetime.now()
        # Setting silent to True causes parsing errors to return None,
        # the errors are themselves swallowed.  See Flask API docs for details.
        event = request.get_json(silent=True)
        if event:
            # We discard events not generated by our configured source bucket
            if event['bucket'] != source_bucket:
                event_stats['cos_error'] = event_stats['cos_error'] + 1
                abort(400)
            event_status = 'OK'
            event_stats['cos'] = event_stats['cos'] + 1
            source_object = event['key']

            logging.info('Event received for file %s in bucket %s',
                         source_object, source_bucket)

            handler = FileHandler(cos_client=cos_client,
                                  source_bucket=source_bucket,
                                  destination_bucket=destination_bucket,
                                  file=source_object)

            try:
                handler.do()
            except COSError:
                event_status = 'Deletion Error'
                # We could return a 500 due to the failure to delete.
                # If you're customizing this code, you'd need to do a little
                # bit of refactoring to maintain the event history, etc. if
                # you decide you want to abort(500) here.
            history_event = {
                'id': 'cos-' + str(event_stats['cos']),
                'timestamp': event_timestamp,
                'objects': [
                    {
                        'key': source_object,
                        'timestamp': datetime.now(),
                        'source_bucket': source_bucket,
                        'destination_bucket': destination_bucket,
                        'status': event_status
                    }
                ]
            }

            # Update our event history and make sure we store the source
            # bucket name
            event_history.append(history_event)
            if source_bucket not in buckets:
                buckets.append(source_bucket)

            return 'OK'
        else:
            event_stats['cos_error'] = event_stats['cos_error'] + 1
            abort(400)

    # Any cron event will trigger reconciliation - any file which is present
    # in the source bucket will be assumed not to have been processed,
    # so we'll process it and transfer it.

    @app.route('/events/cron', methods=['POST'])
    def handle_cron_event():
        # All we check is that the body is valid JSON, nothing beyond that.
        # It would be trivial to check for specific message body elements
        # and probably advisable in a real world application.
        event = request.get_json(silent=True)
        if event:
            event_stats['cron'] = event_stats['cron'] + 1
            event_timestamp = datetime.now()
            history_event = {
                'id': 'cron-' + str(event_stats['cron']),
                'timestamp': event_timestamp,
                'objects': []
            }
            source_inventory = cos_client.get_files_info(
                bucket_name=source_bucket)
            for file in source_inventory.keys():
                object_status = 'OK'
                logging.info('RECONCILE: Processing and transferring %s to %s',
                             file, destination_bucket)
                handler = FileHandler(cos_client=cos_client,
                                      source_bucket=source_bucket,
                                      destination_bucket=destination_bucket,
                                      file=file)

                try:
                    handler.do()
                except COSError:
                    object_status = 'Deletion Error'
                logging.info(
                    'RECONCILE: Processing complete for %s', file)

                history_event['objects'].append({
                    'key': file,
                    'timestamp': datetime.now(),
                    'source_bucket': source_bucket,
                    'destination_bucket': destination_bucket,
                    'status': object_status
                })
            event_history.append(history_event)
            return 'OK'
        else:
            event_stats['cron_error'] = event_stats['cron_error'] + 1
            abort(400)

    return app


@click.command()
@click.option('-d', '--destination-bucket', help='Destination bucket for processing output')
@click.option('-s', '--source-bucket', help='Source bucket for input')
@click.option('-x', '--cos-instance-id', help='COS instance ID')
@click.option('-e', '--cos-endpoint', help='COS endpoint URL')
@click.option('-i', '--iam-endpoint', help='IAM token endpoint')
@click.option('-k', '--api-key', help='IAM API key')
@click.option('-p', '--port', default=8080,
              help='HTTP listener port (defaults to 8080)')
@click.option('-h', '--host', default='0.0.0.0',
              help='Host IP address (set to 127.0.0.1 to disable remote connections, default is 0.0.0.0)')
@click.option('-l', '--log-level', default='info',
              help='Log level (debug|info|warning|error|critical).  The default is info.')
def start_server(destination_bucket,
                 source_bucket,
                 cos_instance_id,
                 cos_endpoint,
                 iam_endpoint,
                 api_key,
                 port,
                 host,
                 log_level):
    """Demo app for processing files and moving between buckets."""

    log_levels = {
        'debug': logging.DEBUG,
        'info': logging.INFO,
        'warning': logging.WARNING,
        'error': logging.ERROR,
        'critical': logging.CRITICAL
    }
    logging.basicConfig(level=log_levels[log_level])
    # Get our config/arguments

    # TODO: Move to click-based environment var handling
    cos_endpoint = cos_endpoint if cos_endpoint else environ.get(
        'COS_ENDPOINT')
    if not cos_endpoint:
        logging.error('No valid COS endpoint specified')
        return -1

    api_key = api_key if api_key else environ.get('APIKEY')
    if not api_key:
        logging.error('No IAM API key found')
        return -1

    destination_bucket = destination_bucket if destination_bucket else environ.get(
        'DESTINATION_BUCKET')
    if not destination_bucket:
        logging.error('Must specify a destination bucket')
        return -1

    source_bucket = source_bucket if source_bucket else environ.get(
        'SOURCE_BUCKET')
    if not source_bucket:
        logging.error('Must specify a source bucket')
        return -1

    cos_instance_id = cos_instance_id if cos_instance_id else environ.get(
        'COS_INSTANCE_ID')
    if not cos_instance_id:
        logging.error('No COS instance ID found')
        return -1

    iam_endpoint = iam_endpoint if iam_endpoint else environ.get(
        'IAM_ENDPOINT')
    if not iam_endpoint:
        logging.error('No IAM endpoint specified')
        return -1

    cos_client = CloudObjectStorage(
        api_key=api_key,
        instance_id=cos_instance_id,
        iam_endpoint=iam_endpoint,
        cos_endpoint=cos_endpoint)

    logging.info('Starting cos-2-cos server')

    server = create_server(cos_client=cos_client,
                           destination_bucket=destination_bucket,
                           source_bucket=source_bucket)
    server.run(port=port)


if __name__ == "__main__":
    exit(start_server())
