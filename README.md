

January => 31

input:
a: 30
b: 30
c: 30

30th January,
send 3 reports

Case 2:

a: 31
b: 30
c: 31

30th January,
send 3 reports

For feb:


For any date other than 30 for other months and 28 for february,

send all reports greater than 30 (all) or 28 (feb)

-- Policy
{
"Version": "2012-10-17",
"Statement": [
    {
        "Sid": "AddPerm",
        "Effect": "Allow",
        "Principal": "*",
        "Action": [
            "s3:PutObject",
            "s3:PutObjectAcl",
            "s3:GetObject"
        ],
        "Resource": "arn:aws:s3:::poc-manjul/*"
        
    }
]
}  
