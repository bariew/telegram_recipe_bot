
CREATE TABLE IF NOT EXISTS `user` (
  `user_id` int(11) NOT NULL,
  `date` date DEFAULT NULL,
  `role` tinyint(4) NOT NULL DEFAULT '0',
  `calls` int(11) NOT NULL DEFAULT '0'
) ENGINE=InnoDB DEFAULT CHARSET=utf8;

ALTER TABLE `user`
  ADD UNIQUE KEY `user_id` (`user_id`);
COMMIT;