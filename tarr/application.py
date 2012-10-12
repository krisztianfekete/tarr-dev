import os.path
from tarr.model import Job
from tarr.compiler import Program
from zope.dottedname.resolve import resolve as dottedname_resolve

import hashlib
from datetime import datetime

import logging


log = logging.getLogger(__name__)


class Application(object):

    ''' Facade of operations of batch data processing using an external, replacable `program`.

    This class is intended to be subclassed for defining the concrete operations.

    Batch: amount of data that can be kept in memory at once for processing.
    Job: collection of Batches, also defines the data source

    '''

    session = None

    program = None
    job = None
    batch = None

    def setup(self):
        '''Override to create application specific schema'''

    def create_job(self, name, program_config, source, partitioning_name, description):
        self.job = Job()

        self.job.job_name = name

        cls = self.__class__
        self.job.application = '{0}.{1}'.format(cls.__module__, cls.__name__)

        self.job.program_config = program_config
        self.job.program_config_hash = self.program_config_hash()
        self.job.source = source
        self.job.partitioning_name = partitioning_name
        self.job.description = description

        self.session.add(self.job)

        self.create_batches()

        self.session.commit()

    def program_config_file(self):
        ''' .job.program_config -> file name '''

        compiled_file = dottedname_resolve(self.job.program_config).__file__
        base, ext = os.path.splitext(compiled_file)
        assert ext in ['.py', '.pyc', '.pyo']
        return base + '.py'

    def program_config_content(self):
        with open(self.program_config_file()) as f:
            return f.read()

    def program_config_hash(self):
        hash = hashlib.sha1()
        hash.update(self.program_config_content())
        return hash.hexdigest()

    def create_batches(self):
        '''Create batch objects for the current job

        As batches are data source specific there is no default implementation
        '''

        pass

    def process_job(self):
        for self.batch in self.job.batches:
            if not self.batch.is_processed:
                self.process_batch()

    def process_batch(self):
        data_items = self.load_data_items()
        processed_data_items = [self.process_data_item(item) for item in data_items]
        self.save_data_items(processed_data_items)

        self.batch.time_completed = datetime.now()
        self.batch.program_config_hash = self.program_config_hash()

        self.save_batch_statistics()

        self.session.commit()

    def load_data_items(self):
        '''(Job, Batch) -> list of data items

        The output should be [tarr.data.Data], i.e. the items must at least contain:
            an id:     constant identifier of the data
            a payload: the real data with or without identifiers, all of them can be potentially modified when processed
        they can contain any more contextual information if needed
        '''

        pass

    def process_data_item(self, data_item):
        try:
            return self.program.run(data_item)
        except:
            try:
                log.exception('process_data_item(%s)', repr(data_item))
            except:
                log.exception('process_data_item - can not log data_item!')
            return data_item

    def save_data_items(self, data_items):
        '''Extract output from data items and store them.

        data_items are like those of returned by load_data_items()
        '''

        pass

    def save_batch_statistics(self):
        self.batch.save_statistics(self.program)

    def merge_batch_statistics(self):
        self.batch.merge_statistics_into(self.program)

    def delete_job(self):
        for self.batch in self.job.batches:
            self.delete_batch()

        self.session.delete(self.job)
        self.session.commit()
        self.job = None

    def delete_batch(self):
        self.session.delete(self.batch)
        self.batch = None

    def load_program(self):
        '''Loads the job's program - the data processing logic'''

        self.program = Program(dottedname_resolve(self.job.program_config).TARR_PROGRAM)
