"""Basic configuration for Sphinx documentation."""

project = 'colcon-distro'
copyright = '2021 Clearpath'
author = 'Mike Purvis'
release = ''
html_theme = 'sphinx_rtd_theme'

extensions = [
    'sphinx_rtd_theme'
]

html_theme_options = {
    'collapse_navigation': False
}
