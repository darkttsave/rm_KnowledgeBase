#include "rclcpp/rclcpp.hpp"
#include "std_msgs/msg/string.hpp"

int main(int argc, char **argv) {
    rclcpp::init(argc, argv);
    auto node = rclcpp::Node::make_shared("talker_node");
    auto pub = node->create_publisher<std_msgs::msg::String>("hello_topic", 10);
    
    rclcpp::WallRate rate(1); // 每秒发一次
    while (rclcpp::ok()) {
        auto msg = std_msgs::msg::String();
        msg.data = "Hello World";
        pub->publish(msg);
        RCLCPP_INFO(node->get_logger(), "已发送: %s", msg.data.c_str());
        rclcpp::spin_some(node);
        rate.sleep();
    }
    rclcpp::shutdown();
    return 0;
}
