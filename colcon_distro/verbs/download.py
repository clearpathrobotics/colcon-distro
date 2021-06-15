from colcon_core.task import TaskContext
from colcon_core.verb import VerbExtensionPoint
from colcon_core.event_handler import add_event_handler_arguments
from colcon_core.executor import add_executor_arguments
from colcon_core.executor import execute_jobs
from colcon_core.executor import Job
from colcon_core.executor import OnError
from colcon_distro.repository_descriptor import RepositoryDescriptor

import os
import pathlib
import yaml

# TODO: Why isn't this working?
import colcon_output.event_handler.summary
colcon_output.event_handler.summary.get_job_type_word_form = lambda n: 'repository' if n == 1 else 'repositories'


class DownloadVerb(VerbExtensionPoint):
    class Task:
        def set_context(self, context):
            self.context = context

        async def __call__(self):
            # Lazy-import this so we don't pay the cost of importing
            # its dependencies when it isn't used.
            from colcon_distro.download import GitRev
            spec = self.context.repo_spec
            package_paths = [p['path'] for p in spec['packages'].values()]
            path = self.context.src_path / self.context.repo_name
            path.mkdir(parents=True, exist_ok=True)
            distro_descriptor = RepositoryDescriptor()
            distro_descriptor.url = spec['url']
            distro_descriptor.type = 'git'
            distro_descriptor.version = spec['version']
            gitrev = GitRev(distro_descriptor)
            await gitrev.downloader.download_all_to(path, limit_paths=package_paths)

    def __init__(self):  # noqa: D107
        super().__init__()

    def add_arguments(self, *, parser):  # noqa: D102
        parser.add_argument('--input-file', '-i', default='.workspace',
                            help='YAML file to load repository list from.')
        parser.add_argument('--src-base', '-s', default='src',
                            help='Path to unpack repo tarballs to.')
        add_executor_arguments(parser)
        add_event_handler_arguments(parser)

    def main(self, *, context):  # noqa: D102
        src_path = pathlib.Path(os.path.abspath(context.args.src_base))

        with open(context.args.input_file) as f:
            repositories = yaml.safe_load(f)['repositories']

        class Dummy:
            def __init__(self, name):
                self.name = name

        jobs = {}
        for repo_name, repo_spec in repositories.items():
            task_context = TaskContext(args=context.args, pkg=Dummy(repo_name), dependencies=set())
            task_context.repo_name = repo_name
            task_context.repo_spec = repo_spec
            task_context.src_path = src_path

            job = Job(
                identifier=repo_name,
                dependencies=[],
                task=self.Task(), task_context=task_context)
            jobs[repo_name] = job
        rc = execute_jobs(context, jobs, on_error=OnError.interrupt)
        return rc
