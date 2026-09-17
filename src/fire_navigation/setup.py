import os
from glob import glob

from setuptools import find_packages, setup

package_name = 'fire_navigation'

setup(
    name=package_name,
    version='0.1.0',
    packages=find_packages(exclude=['test']),
    data_files=[
        ('share/ament_index/resource_index/packages',
            ['resource/' + package_name]),
        ('share/' + package_name, ['package.xml']),
        (os.path.join('share', package_name, 'config'), glob('config/*.yaml')),
        (os.path.join('share', package_name, 'scripts'), glob('scripts/*.py')),
    ],
    install_requires=['setuptools'],
    zip_safe=True,
    maintainer='eom',
    maintainer_email='kmh9178@inha.edu',
    description='laser filter, EKF, AMCL, Nav2, 웨이포인트 순찰 노드/설정',
    license='Apache-2.0',
    entry_points={
        'console_scripts': [
            'patrol_node = fire_navigation.patrol_node:main',
            'sync_waypoints = fire_navigation.sync_waypoints:main',
        ],
    },
)
