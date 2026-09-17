cmake_minimum_required(VERSION 3.8)
project(fire_world)

find_package(ament_cmake REQUIRED)

install(DIRECTORY config worlds maps models scripts
  DESTINATION share/${PROJECT_NAME}
  USE_SOURCE_PERMISSIONS
)

ament_package()
