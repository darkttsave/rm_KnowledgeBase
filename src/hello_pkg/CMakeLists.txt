cmake_minimum_required(VERSION 3.8)
project(hello_pkg)

# --- 1. 查找依赖 (必须放在最前面) ---
find_package(ament_cmake REQUIRED)
find_package(rclcpp REQUIRED)
find_package(std_msgs REQUIRED)

# --- 2. 设置编译选项 ---
if(CMAKE_COMPILER_IS_GNUCXX OR CMAKE_CXX_COMPILER_ID MATCHES "Clang")
  add_compile_options(-Wall -Wextra -Wpedantic)
endif()

# --- 3. 定义可执行文件 (Talker & Listener) ---
# 每一个二进制文件都需要 add_executable + ament_target_dependencies
add_executable(talker1 src/talker1.cpp)
ament_target_dependencies(talker1 rclcpp std_msgs)

add_executable(listener1 src/listener1.cpp)
ament_target_dependencies(listener1 rclcpp std_msgs)

# --- 4. 设置安装出口 (必须在 if(BUILD_TESTING) 之外) ---
# 没有这一步，ros2 run 就找不到你的 talker/listener
install(TARGETS
  talker1
  listener1
  DESTINATION lib/${PROJECT_NAME}
)

# --- 5. 测试环境 (仅用于单元测试，别把主程序放这里) ---
if(BUILD_TESTING)
  find_package(ament_lint_auto REQUIRED)
  set(ament_cmake_copyright_FOUND TRUE)
  set(ament_cmake_cpplint_FOUND TRUE)
  ament_lint_auto_find_test_dependencies()
endif()

# --- 6. 结尾标记 (必须在最后一行) ---
ament_package()
#123