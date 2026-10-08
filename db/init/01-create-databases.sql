-- Chạy tự động MỘT LẦN khi volume pgdata còn trống.
-- Muốn chạy lại (xóa sạch dữ liệu): docker compose down -v
-- Mỗi service có database riêng; service chỉ được kết nối vào database của mình.
CREATE DATABASE user_db;
CREATE DATABASE tuition_db;
CREATE DATABASE payment_db;
