#include "rclcpp/rclcpp.hpp"
#include "std_msgs/msg/string.hpp"

int main(int argc, char **argv) {
    rclcpp::init(argc, argv);
    auto node = rclcpp::Node::make_shared("listener_node");
    auto sub = node->create_subscription<std_msgs::msg::String>(
        "hello_topic", 10, [&](const std_msgs::msg::String::SharedPtr msg) {
            RCLCPP_INFO(node->get_logger(), "收到: %s", msg->data.c_str());
        });
    rclcpp::spin(node);
    rclcpp::shutdown();
    return 0;
}