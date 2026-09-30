INSERT INTO customers VALUES
(1, 'Aarav Sharma', '1988-04-12', 'Mumbai', 'Maharashtra',
 'aarav.sharma@example.com', '9000000001', '2021-01-15'),
(2, 'Meera Iyer', '1992-08-21', 'Pune', 'Maharashtra',
 'meera.iyer@example.com', '9000000002', '2022-03-10'),
(3, 'Rohan Verma', '1985-11-05', 'Delhi', 'Delhi',
 'rohan.verma@example.com', '9000000003', '2020-07-19'),
(4, 'Sneha Patil', '1990-06-17', 'Mumbai', 'Maharashtra',
 'sneha.patil@example.com', '9000000004', '2023-02-25'),
(5, 'Vikram Singh', '1979-02-09', 'Jaipur', 'Rajasthan',
 'vikram.singh@example.com', '9000000005', '2019-09-12'),
(6, 'Ananya Rao', '1995-12-30', 'Bengaluru', 'Karnataka',
 'ananya.rao@example.com', '9000000006', '2024-01-05');

INSERT INTO agents VALUES
(101, 'Rajesh Kumar', 'Mumbai Central Branch', 'Mumbai',
 '2018-05-12', 'Active'),
(102, 'Priya Nair', 'Pune East Branch', 'Pune',
 '2020-09-01', 'Active'),
(103, 'Amit Joshi', 'Delhi North Branch', 'Delhi',
 '2017-03-15', 'Inactive');

INSERT INTO policies VALUES
(1001, 'POL-2023-001', 1, 101, 'Secure Life Plus',
 'Term Insurance', 10000000, 25000, '2023-01-10',
 '2043-01-09', 'Active'),
(1002, 'POL-2022-002', 2, 102, 'Wealth Builder',
 'Endowment', 2500000, 60000, '2022-04-01',
 '2042-03-31', 'Active'),
(1003, 'POL-2021-003', 3, 103, 'Family Protection Plan',
 'Term Insurance', 7500000, 22000, '2021-07-15',
 '2041-07-14', 'Lapsed'),
(1004, 'POL-2024-004', 4, 101, 'Secure Life Plus',
 'Term Insurance', 5000000, 18000, '2024-02-20',
 '2044-02-19', 'Active'),
(1005, 'POL-2020-005', 5, 103, 'Guaranteed Income Plan',
 'Savings', 3000000, 75000, '2020-10-01',
 '2035-09-30', 'Matured'),
(1006, 'POL-2024-006', 6, 102, 'Child Future Plan',
 'Child Plan', 2000000, 45000, '2024-05-10',
 '2042-05-09', 'Active'),
(1007, 'POL-2025-007', 1, 101, 'Retirement Advantage',
 'Pension', 4000000, 80000, '2025-01-15',
 '2045-01-14', 'Active');

INSERT INTO premium_payments VALUES
(5001, 1001, '2025-01-10', '2025-01-08', 25000, 'Paid', 'UPI'),
(5002, 1002, '2025-04-01', '2025-04-03', 60000, 'Paid', 'Net Banking'),
(5003, 1003, '2025-07-15', NULL, 22000, 'Overdue', NULL),
(5004, 1004, '2025-02-20', '2025-02-20', 18000, 'Paid', 'Auto Debit'),
(5005, 1005, '2025-10-01', NULL, 75000, 'Not Applicable', NULL),
(5006, 1006, '2025-05-10', NULL, 45000, 'Overdue', NULL),
(5007, 1007, '2026-01-15', '2026-01-14', 80000, 'Paid', 'Auto Debit');

INSERT INTO claims VALUES
(7001, 1001, 'Hospitalisation', '2025-02-12', 150000,
 'Settled', '2025-02-25', NULL),
(7002, 1002, 'Death Claim', '2025-06-18', 2500000,
 'Under Review', NULL, NULL),
(7003, 1003, 'Death Claim', '2024-11-01', 7500000,
 'Rejected', NULL, 'Policy was not active on the date of claim'),
(7004, 1004, 'Hospitalisation', '2025-08-10', 80000,
 'Approved', NULL, NULL),
(7005, 1006, 'Critical Illness', '2025-09-05', 500000,
 'Pending Documents', NULL, NULL);
