from colcon_core.command import main as colcon_main
from tempfile import TemporaryDirectory

import os


download_spec = """
repositories:
  catkin:
    type: git
    url: https://github.com/ros/catkin.git
    version: 4fe89dd8a553a74e16e14754021e6550386fe5
    packages:
      catkin:
        path: .
        type: ros.cmake
"""


def test_call_download():
    cwd = os.getcwd()
    with TemporaryDirectory() as test_dir:
        os.chdir(test_dir)
        with open('.workspace', 'w') as f:
            f.write(download_spec)
        assert colcon_main(argv=['download']) == 0
        assert os.path.exists('src/catkin/cmake')
    os.chdir(cwd)
