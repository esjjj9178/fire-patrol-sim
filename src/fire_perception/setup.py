import os
from glob import glob

from setuptools import find_packages, setup

package_name = 'fire_perception'

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
        (os.path.join('share', package_name, 'models'), glob('models/*.pt')),
    ],
    install_requires=['setuptools'],
    zip_safe=True,
    maintainer='eom',
    maintainer_email='kmh9178@inha.edu',
    description='비전(HSV/YOLO) 화재 검출, 카메라 팬 제어, 데이터셋/학습 도구',
    license='Apache-2.0',
    tests_require=['pytest'],
    entry_points={
        'console_scripts': [
            'camera_pan_node = fire_perception.camera_pan_node:main',
            'vision_node = fire_perception.vision_node:main',
            'thermal_node = fire_perception.thermal_node:main',
            'virtual_thermal_node = fire_perception.virtual_thermal_node:main',
            'gas_sim_node = fire_perception.gas_sim_node:main',
            'collect_images = fire_perception.tools.collect_images:main',
            'auto_label = fire_perception.tools.auto_label:main',
            'train_yolo = fire_perception.tools.train_yolo:main',
            'eval_yolo = fire_perception.tools.eval_yolo:main',
            'sensor_scenario_test = fire_perception.tools.sensor_scenario_test:main',
        ],
    },
)
