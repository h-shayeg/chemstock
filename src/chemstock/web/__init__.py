"""The Persian web pages (right-to-left), served by the same app as the API.

Pages live under /ui. They use the same database, the same users and the same
reports as the API; only the way of logging in differs: the access token is
kept in an HttpOnly cookie instead of an Authorization header.

Everything the pages need (style sheet, font) is served by the app itself, so
they work on a computer without internet access.
"""
