import os
from glob import glob

from setuptools import find_packages, setup

package_name = 'fire_iot_bridge'

setup(
    name=package_name,
    version='0.1.0',
    packages=find_packages(exclude=['test']),
    data_files=[
        ('share/ament_index/resource_index/packages',
            ['resource/' + package_name]),
        ('share/' + package_name, ['package.xml']),
        (os.path.join('share', package_name, 'config'), glob('config/*.yaml')),
    ],
    install_requires=['setuptools'],
    zip_safe=True,
    maintainer='eom',
    maintainer_email='kmh9178@inha.edu',
    description='MQTT 브리지(설계 + 비활성 스텁)',
    license='Apache-2.0',
    entry_points={
        'console_scripts': [
            'mqtt_bridge_node = fire_iot_bridge.mqtt_bridge_node:main',
        ],
    },
)
