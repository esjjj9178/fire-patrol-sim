import os
from glob import glob

from setuptools import find_packages, setup

package_name = 'fire_fusion'

setup(
    name=package_name,
    version='0.1.0',
    packages=find_packages(exclude=['test']),
    data_files=[
        ('share/ament_index/resource_index/packages',
            ['resource/' + package_name]),
        ('share/' + package_name, ['package.xml']),
        (os.path.join('share', package_name, 'config'), glob('config/*.yaml')),
        (os.path.join('share', package_name, 'launch'), glob('launch/*.launch.py')),
    ],
    install_requires=['setuptools'],
    zip_safe=True,
    maintainer='eom',
    maintainer_email='kmh9178@inha.edu',
    description='가중치 신뢰도 융합 + 임무 관리 상태머신',
    license='Apache-2.0',
    entry_points={
        'console_scripts': [
            'fusion_node = fire_fusion.fusion_node:main',
            'mission_manager_node = fire_fusion.mission_manager_node:main',
        ],
    },
)
