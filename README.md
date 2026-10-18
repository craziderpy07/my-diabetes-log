# My Diabetes Log

A Flask web app that puts glucose, meal, exercise, and medication records into one timeline.  

I created this web app thinking of my dad as he had diabetes, but growing up, I saw that he never tracked what he was doing. I've never seen that man write down his glucose readings and barely knew about his A1C readings. I am hoping to further expand this project, so it may possibly be used personally by others!  
> [!NOTE]
> **Educational prototype: use fictional data only. Not a medical tool.**

## Features
- Sign up with a username and email, then log in with either one
- Add, edit, and delete records; filter by date and type
- Timeline with 5 records per page and a glucose average
- Personal Information page to update your username, email, and password
- Neon PostgreSQL database, hashed passwords, CSRF protection

> [!IMPORTANT]
> Deployed on Vercel: [My Diabetes Log](https://my-diabetes-log.vercel.app/)

## Further planned updates:
- Possible graphing overview of daily, weekly, monthly, and yearly glucose readings.
- Further enhancements of Personal Information page for additional user informations.
- Currently in-progress of in-depth research about diabetes!

## Notes
- Times are entered and shown in Pacific time and stored as UTC.
- Algorithms used: min-heap merge, binary-search date ranges, hash-map grouping, two-pointer rolling averages.
- Not ready for real patient data. It would first need email verification, rate limiting, password recovery, and a security eview.