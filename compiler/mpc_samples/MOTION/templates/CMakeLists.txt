cmake_minimum_required(VERSION 3.12)
cmake_policy(SET CMP0075 NEW)
project(TEMPLATE_CODE CXX)
set(CMAKE_BUILD_TYPE Debug)

add_subdirectory(/opt/mp_opa/backend_submodules/MOTION /opt/mp_opa/backend_submodules/MOTION/build)

add_executable(template_code main.cpp collect_stats.cpp)

find_package(Boost COMPONENTS program_options REQUIRED)

target_include_directories(template_code PUBLIC ${Boost_INCLUDE_DIRS})
target_link_libraries(template_code
    MOTION::motion
    Boost::program_options
    ${Boost_LIBRARIES}
)

# vim: set ft=cmake :

# Emacs:
# Local Variables:
# mode: cmake
# End: