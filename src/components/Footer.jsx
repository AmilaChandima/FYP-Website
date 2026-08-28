import { Facebook, Instagram, Linkedin, Mail, MapPin, Phone, Twitter, Zap } from "lucide-react";
import { Link } from "react-router-dom";

export default function Footer() {
  return (
    <footer className="footer">
      <div className="footer-grid">
        <section>
          <div className="brand footer-brand">
            <span className="brand-mark"><Zap size={22} /></span>
            <span>
              <strong>Solar<span>Charge</span></strong>
              <small>Smart EV Fast Charging</small>
            </span>
          </div>
          <p>Powering the future with intelligent charging technology and clean energy.</p>
        </section>

        <section>
          <h4>Quick Links</h4>
          <Link to="/dashboard">Dashboard</Link>
          <Link to="/pricing">Pricing</Link>
          <Link to="/chargers">Chargers</Link>
          <Link to="/about">About Us</Link>
        </section>

        <section>
          <h4>Contact Us</h4>
          <p><Mail size={16} /> support@solarcharge.com</p>
          <p><Phone size={16} /> +94 77 123 4567</p>
          <p><MapPin size={16} /> Colombo, Sri Lanka</p>
        </section>

        <section>
          <h4>Follow Us</h4>
          <div className="socials">
            <a href="#" aria-label="Facebook"><Facebook size={18} /></a>
            <a href="#" aria-label="Twitter"><Twitter size={18} /></a>
            <a href="#" aria-label="LinkedIn"><Linkedin size={18} /></a>
            <a href="#" aria-label="Instagram"><Instagram size={18} /></a>
          </div>
        </section>

        <section>
          <h4>Stay Updated</h4>
          <p>Get pricing and station availability updates.</p>
          <form className="subscribe" onSubmit={(event) => event.preventDefault()}>
            <input type="email" placeholder="Enter your email" aria-label="Email" />
            <button>Subscribe</button>
          </form>
        </section>
      </div>

      <div className="footer-bottom">
        <span>© {new Date().getFullYear()} SolarCharge Station. All rights reserved.</span>
        <span>Privacy Policy&nbsp;&nbsp; | &nbsp;&nbsp;Terms of Service</span>
      </div>
    </footer>
  );
}
