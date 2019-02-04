from setuptools import setup, find_packages

setup(name='bjointsp',
    version='2.4.1',
    license='Apache 2.0',
    description='B-JointSP provides algorithms for joint scaling and placement of uni- or bidirectional network services',
    url='https://github.com/CN-UPB/B-JointSP',
    author='Stefan Schneider',
    author_email='stefan.schneider@upb.de',
    package_dir={'':'src'},
    packages=find_packages('src'),
    install_requires=[
        "networkx",
        "geopy",
        "pyyaml",
        "numpy"
    ],
    zip_safe=False,
    entry_points={
        'console_scripts': [
            'bjointsp=bjointsp.main:main',
        ],
    },
)
