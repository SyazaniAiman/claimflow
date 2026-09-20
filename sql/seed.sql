-- Synthetic data only.  No real customer information is used anywhere.
INSERT INTO policies
 (policy_no, holder_name, holder_ic, product, active, coverage_limit, age_days, claims_last_90d)
VALUES
 ('POL-MTR-1001', N'Aisyah binti Rahman', '900101-14-5566', 'MOTOR',  1,  60000.00, 730, 0),
 ('POL-MTR-1002', N'Chong Wei Ming',      '880712-08-1234', 'MOTOR',  1,  45000.00, 400, 1),
 ('POL-MTR-1003', N'Ravi a/l Kumaran',    '950320-10-7788', 'MOTOR',  1,  30000.00,  12, 0),
 ('POL-TRV-2001', N'Nurul Huda binti Ali','920505-06-9911', 'TRAVEL', 1,  15000.00, 200, 0),
 ('POL-TRV-2002', N'Lim Siew Fong',       '870909-07-2233', 'TRAVEL', 0,  15000.00, 900, 0);
GO
