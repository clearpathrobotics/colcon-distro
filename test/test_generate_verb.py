from colcon_core.command import main as colcon_main
from tempfile import TemporaryDirectory

import os
import responses
import yaml


response = {
    'repositories': {
        'foo': {
            'url': 'url/to/foo',
            'type': 'git',
            'version': '1.2.3',
            'packages': [{
                'name': 'baz',
                'path': 'thing/baz',
                'type': 'baztype',
                'depends': {}
            }]
        }
    }
}


@responses.activate
def test_call_generate():
    cwd = os.getcwd()
    responses.add(responses.GET, 'http://example.com/get/banana/foo/bar.json', json=response)
    with TemporaryDirectory() as test_dir:
        os.chdir(test_dir)
        colcon_main(argv=[
            'generate',
            '--colcon-cache', 'http://example.com',
            '--ref', 'foo/bar',
            '--rosdistro', 'banana',
            '--output-file', 'output.yaml',
            'baz'
        ])
        with open('output.yaml') as f:
            y = yaml.safe_load(f)
            assert y['repositories']['foo']['url'] == 'url/to/foo'
    os.chdir(cwd)
