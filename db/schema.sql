CREATE TABLE IF NOT EXISTS customers (
    customer_id INTEGER PRIMARY KEY,
    customer_name VARCHAR(100) NOT NULL,
    date_of_birth DATE,
    city VARCHAR(50),
    state VARCHAR(50),
    email VARCHAR(100),
    mobile_number VARCHAR(15),
    customer_since DATE
);

CREATE TABLE IF NOT EXISTS agents (
    agent_id INTEGER PRIMARY KEY,
    agent_name VARCHAR(100) NOT NULL,
    branch_name VARCHAR(100),
    city VARCHAR(50),
    joining_date DATE,
    status VARCHAR(20)
);

CREATE TABLE IF NOT EXISTS policies (
    policy_id INTEGER PRIMARY KEY,
    policy_number VARCHAR(30) UNIQUE NOT NULL,
    customer_id INTEGER NOT NULL,
    agent_id INTEGER,
    product_name VARCHAR(100),
    policy_type VARCHAR(50),
    sum_assured DECIMAL(15,2),
    annual_premium DECIMAL(12,2),
    policy_start_date DATE,
    policy_end_date DATE,
    policy_status VARCHAR(20),
    FOREIGN KEY (customer_id) REFERENCES customers(customer_id),
    FOREIGN KEY (agent_id) REFERENCES agents(agent_id)
);

CREATE TABLE IF NOT EXISTS premium_payments (
    payment_id INTEGER PRIMARY KEY,
    policy_id INTEGER NOT NULL,
    premium_due_date DATE,
    payment_date DATE,
    premium_amount DECIMAL(12,2),
    payment_status VARCHAR(20),
    payment_mode VARCHAR(30),
    FOREIGN KEY (policy_id) REFERENCES policies(policy_id)
);

CREATE TABLE IF NOT EXISTS claims (
    claim_id INTEGER PRIMARY KEY,
    policy_id INTEGER NOT NULL,
    claim_type VARCHAR(50),
    claim_date DATE,
    claim_amount DECIMAL(15,2),
    claim_status VARCHAR(30),
    settlement_date DATE,
    rejection_reason VARCHAR(255),
    FOREIGN KEY (policy_id) REFERENCES policies(policy_id)
);
